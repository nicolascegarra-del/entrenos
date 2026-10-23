import base64
import os
from datetime import UTC, date, datetime

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pywebpush import WebPushException
from sqlmodel import Session, select

from app.core.security import create_token
from app.models import AppSetting, NotificationLog, NotificationPrefs, PlannedSession, PushSubscription, User
from app.services import notifications as svc

FCM = "https://fcm.googleapis.com/fcm/send/abc123"


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _browser_keys() -> dict:
    """Claves como las que genera un navegador al suscribirse (P-256 + secreto de 16 bytes)."""
    key = ec.generate_private_key(ec.SECP256R1())
    raw = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return {"p256dh": _b64(raw), "auth": _b64(os.urandom(16))}


def _subscribe(session: Session, user: User, endpoint: str = FCM) -> PushSubscription:
    keys = _browser_keys()
    svc.subscribe(session, user.id, endpoint, keys["p256dh"], keys["auth"], "Chrome Android")
    return session.exec(select(PushSubscription).where(PushSubscription.endpoint == endpoint)).one()


@pytest.fixture
def sent(monkeypatch):
    """Simula el servicio push y guarda lo enviado."""
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(svc, "deliver", lambda sub, payload, vapid, subject: calls.append((sub.endpoint, payload)))
    return calls


@pytest.mark.parametrize(("endpoint", "ok"), [
    (FCM, True),
    ("https://updates.push.services.mozilla.com/wpush/v2/x", True),
    ("https://web.push.apple.com/abc", True),
    ("https://wns2-db5p.notify.windows.com/w/?token=x", True),
    ("http://fcm.googleapis.com/fcm/send/x", False),
    ("https://169.254.169.254/latest", False),
    ("https://evil-fcm.googleapis.com.attacker.com/x", False),
])  # fmt: skip
def test_solo_servicios_push_conocidos(endpoint, ok):
    assert svc.allowed_endpoint(endpoint) is ok


def test_claves_vapid_se_crean_una_vez_y_cifradas(client, user, session):
    first = client.get("/api/v1/notifications", headers=auth(user)).json()
    second = client.get("/api/v1/notifications", headers=auth(user)).json()
    assert first["public_key"] == second["public_key"] and len(first["public_key"]) == 87
    stored = session.get(AppSetting, svc.VAPID_SETTING).value
    assert "PRIVATE KEY" not in stored
    assert first["prefs"]["daily_hour"] == 7 and first["devices"] == []


def test_suscribir_valida_servicio_y_guarda_zona(client, user):
    body = {"endpoint": "https://intranet.local/hook", "keys": _browser_keys()}
    assert client.post("/api/v1/notifications/subscriptions", json=body, headers=auth(user)).status_code == 422
    body = {"endpoint": FCM, "keys": _browser_keys(), "user_agent": "Pixel", "timezone": "America/Mexico_City"}
    data = client.post("/api/v1/notifications/subscriptions", json=body, headers=auth(user)).json()
    assert data["devices"][0]["endpoint_host"] == "fcm.googleapis.com"
    assert data["prefs"]["timezone"] == "America/Mexico_City"
    data = client.post("/api/v1/notifications/subscriptions/remove", json={"endpoint": FCM}, headers=auth(user)).json()
    assert data["devices"] == []


def test_dispositivo_cambia_de_cuenta(session, user):
    other = User(email="otra@example.com", password_hash="x")
    session.add(other)
    session.commit()
    _subscribe(session, user)
    sub = _subscribe(session, other)
    assert sub.user_id == other.id and len(session.exec(select(PushSubscription)).all()) == 1


def test_prueba_sin_dispositivos_y_con_dispositivo(client, user, session, sent):
    assert client.post("/api/v1/notifications/test", headers=auth(user)).status_code == 409
    _subscribe(session, user)
    assert client.post("/api/v1/notifications/test", headers=auth(user)).json() == {"sent": 1, "failed": 0}
    assert '"url": "/ajustes"' in sent[0][1]


def test_quitar_dispositivo_ajeno_404(client, user, session):
    other = User(email="otra@example.com", password_hash="x")
    session.add(other)
    session.commit()
    sub = _subscribe(session, other)
    assert client.delete(f"/api/v1/notifications/devices/{sub.id}", headers=auth(user)).status_code == 404
    assert client.delete(f"/api/v1/notifications/devices/{sub.id}", headers=auth(other)).status_code == 204


def test_preferencias(client, user):
    prefs = {"daily_session": False, "daily_hour": 20, "timezone": "Europe/Madrid", "overload": True,
             "sync_error": False, "achievements": True, "plan_changes": True, "activity_reviews": False}  # fmt: skip
    data = client.put("/api/v1/notifications/prefs", json=prefs, headers=auth(user)).json()
    assert data["prefs"] == prefs
    bad = {**prefs, "timezone": "Marte/Olympus"}
    assert client.put("/api/v1/notifications/prefs", json=bad, headers=auth(user)).status_code == 422


def test_suscripcion_caducada_se_borra(session, user, monkeypatch):
    _subscribe(session, user)

    class Gone:
        status_code = 410

    def fail(*_):
        raise WebPushException("gone", response=Gone())

    monkeypatch.setattr(svc, "deliver", fail)
    assert svc.push(session, user.id, "t", "b") == {"sent": 0, "failed": 1}
    assert session.exec(select(PushSubscription)).all() == []


def test_fallo_de_red_no_borra(session, user, monkeypatch):
    _subscribe(session, user)
    monkeypatch.setattr(svc, "deliver", lambda *_: (_ for _ in ()).throw(ConnectionError()))
    assert svc.push(session, user.id, "t", "b") == {"sent": 0, "failed": 1}
    assert len(session.exec(select(PushSubscription)).all()) == 1


def test_aviso_respeta_preferencias_y_no_se_repite(session, user, sent):
    _subscribe(session, user)
    assert svc.notify(session, user.id, "sync_error", "k1", "T", "B") is True
    assert svc.notify(session, user.id, "sync_error", "k1", "T", "B") is False  # misma clave
    session.add(NotificationPrefs(user_id=user.id, sync_error=False))
    session.commit()
    assert svc.notify(session, user.id, "sync_error", "k2", "T", "B") is False
    assert len(sent) == 1 and len(session.exec(select(NotificationLog)).all()) == 1


def test_sin_dispositivos_no_registra(session, user):
    assert svc.notify(session, user.id, "overload", "k", "T", "B") is False
    assert session.exec(select(NotificationLog)).all() == []


def test_sesion_del_dia_a_la_hora_elegida(session, user, sent):
    _subscribe(session, user)
    session.add(PlannedSession(user_id=user.id, day=date(2026, 10, 22), sport="running", title="Rodaje suave"))
    session.commit()
    at_7_madrid = datetime(2026, 10, 22, 5, 10, tzinfo=UTC)  # 07:10 en Madrid (CEST)
    assert svc.daily_session(session, user.id, datetime(2026, 10, 22, 9, 0, tzinfo=UTC)) is False  # otra hora
    assert svc.daily_all(session, at_7_madrid) == 1
    assert svc.daily_all(session, at_7_madrid) == 0  # una vez al día
    assert "Hoy toca: Rodaje suave" in sent[0][1]


def test_sesion_del_dia_sin_plan_no_avisa(session, user, sent):
    _subscribe(session, user)
    assert svc.daily_session(session, user.id, datetime(2026, 10, 22, 5, 0, tzinfo=UTC)) is False


def test_sobrecarga_una_vez_por_semana(session, user, sent):
    _subscribe(session, user)
    checks = [{"status": "good", "title": "x", "message": "y"}, {"status": "alert", "title": "Pico", "message": "Baja"}]
    report = {"status": "alert", "checks": checks}
    assert svc.overload(session, user.id, {"status": "watch", "checks": []}) is False
    assert svc.overload(session, user.id, report, date(2026, 10, 19)) is True
    assert svc.overload(session, user.id, report, date(2026, 10, 22)) is False
    assert svc.overload(session, user.id, report, date(2026, 10, 26)) is True


def test_sync_fallida_y_plan(session, user, sent):
    _subscribe(session, user)
    assert svc.sync_failed(session, user.id, True, date(2026, 10, 22)) is True
    assert "caducado" in sent[-1][1]
    assert svc.plan_changed(session, user.id, 3, 5, "Semana cumplida: subimos un poco.") is True
    assert '"url": "/plan/entrenamiento"' in sent[-1][1]


def test_envio_real_cifra_y_firma(session, user, monkeypatch):
    """Sin simular `deliver`: comprueba el cifrado aes128gcm y la cabecera VAPID que salen hacia FCM."""
    sub = _subscribe(session, user)
    captured = {}

    class Ok:
        status_code = 201
        text = ""
        headers: dict = {}

    def fake_post(url, data=None, headers=None, timeout=None, **_):
        captured.update(url=url, data=data, headers=headers)
        return Ok()

    import pywebpush

    monkeypatch.setattr(pywebpush.requests, "post", fake_post)
    vapid, public = svc.vapid_keys(session)
    svc.deliver(sub, '{"title": "hola"}', vapid, "mailto:admin@example.com")
    assert captured["url"] == FCM and captured["headers"]["content-encoding"] == "aes128gcm"
    authz = captured["headers"]["authorization"]
    assert authz.startswith("vapid t=") and f"k={public}" in authz
    assert b"hola" not in captured["data"]  # va cifrado
