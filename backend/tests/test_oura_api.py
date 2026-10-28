import json
import time
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlmodel import select

from app.models import (
    Activity,
    DailyMetric,
    DailySeries,
    HealthTag,
    OuraConnection,
    OuraWebhookSubscription,
    RestPeriod,
    WellnessSession,
)
from app.services import accounts, modules, oura_sync, oura_webhooks
from app.services.sync_service import sync_daily
from tests.fakes import FakeGarmin
from tests.oura_fake import CLIENT_SECRET, DAY, auth, connect
from tests.test_oura_sync import _load_all

WEBHOOK = "/api/v1/sources/oura/webhook"


@pytest.fixture
def synced(session, user, oura):
    connect(session, user)
    _load_all(oura)
    oura_sync.sync_range(session, user.id, DAY, DAY)
    return user


# ─── Contratos de las vistas de salud ────────────────────────────────────────


def test_night_cuando_hay_oura_entonces_contrato_completo(client, synced):
    data = client.get(f"/api/v1/health/night/{DAY}", headers=auth(synced)).json()
    assert set(data) == {"day", "source", "main", "naps", "hypnogram", "hr", "hrv", "sleep_score",
                         "sleep_contributors", "readiness", "sleep_time", "spo2", "tags"}  # fmt: skip
    assert data["day"] == DAY.isoformat() and data["source"] == "oura"
    assert set(data["main"]) == {"type", "bedtime_start", "bedtime_end", "total_sleep_s", "deep_s", "rem_s",
                                 "light_s", "awake_s", "latency_s", "efficiency", "time_in_bed_s", "avg_hr",
                                 "lowest_hr", "avg_hrv", "avg_breath", "restless_periods"}  # fmt: skip
    assert data["main"]["total_sleep_s"] == 27000 and data["main"]["lowest_hr"] == 46
    assert [n["total_sleep_s"] for n in data["naps"]] == [1800]
    assert data["hypnogram"] == {"start": "2026-10-19T23:30:00+02:00", "interval_s": 300, "phases": "4221133214"}
    assert data["hr"] == {"start": "2026-10-19T23:30:00+02:00", "interval_s": 300.0,
                          "items": [55, None, 50, 48, 47, 49]}  # fmt: skip
    assert data["hrv"]["items"][0] == 40
    assert data["sleep_score"] == 82 and data["sleep_contributors"]["timing"] == 80
    assert data["readiness"]["score"] == 76 and data["readiness"]["temperature_trend_deviation"] == 0.05
    assert data["readiness"]["contributors"]["recovery_index"] == 66
    assert data["sleep_time"]["status"] == "optimal_found" and data["sleep_time"]["optimal_bedtime"]["day_tz"] == 7200
    assert data["spo2"] == {"average": 96.8, "breathing_disturbance_index": 4}
    assert {t["label"] for t in data["tags"]} == {"Alcohol", "Cena tarde"}
    assert set(data["tags"][0]) == {"start", "end", "label", "comment"}


def test_night_cuando_solo_reloj_entonces_resumen_del_reloj(client, session, user):
    session.add(DailyMetric(user_id=user.id, day=DAY, metrics={"sleep_seconds": 25000, "sleep_score": 70},
                            raw={"_sources": {"garmin": {"sleep_seconds": 25000, "sleep_score": 70}}},
                            metric_sources={"sleep_seconds": "garmin", "sleep_score": "garmin"}))  # fmt: skip
    session.commit()
    data = client.get(f"/api/v1/health/night/{DAY}", headers=auth(user)).json()
    assert data["source"] == "garmin" and data["main"]["total_sleep_s"] == 25000 and data["hypnogram"] is None
    assert data["sleep_score"] == 70 and data["readiness"] is None and data["naps"] == []


def test_night_cuando_sin_datos_entonces_vacio(client, user):
    data = client.get(f"/api/v1/health/night/{DAY}", headers=auth(user)).json()
    assert data["source"] is None and data["main"] is None and data["tags"] == []


def test_day_cuando_hay_oura_entonces_contrato_completo(client, synced):
    data = client.get(f"/api/v1/health/day/{DAY}", headers=auth(synced)).json()
    assert set(data) == {"day", "heartrate", "activity", "stress", "resilience", "sessions", "tags", "rest_mode"}
    # Día local (+02:00): de las 22:00 UTC del 19 a las 22:00 UTC del 20.
    assert [p[1:] for p in data["heartrate"]] == [[70, "awake"], [150, "workout"], [170, "workout"]]
    assert isinstance(data["heartrate"][0][0], int)
    act = data["activity"]
    assert set(act) == {"score", "steps", "active_calories", "total_calories", "high_s", "medium_s", "low_s",
                        "sedentary_s", "non_wear_s", "class_5min", "met"}  # fmt: skip
    assert act["steps"] == 11200 and act["class_5min"]["classes"] == "0011223344"
    assert act["met"] == {"start": "2026-10-20T04:00:00+02:00", "interval_s": 60.0, "items": [0.9, 1.2, 3.5]}
    assert data["stress"] == {"stress_high_s": 3600, "recovery_high_s": 5400, "day_summary": "normal"}
    assert data["resilience"]["level"] == "solid" and data["resilience"]["contributors"]["stress"] == 60
    assert data["sessions"] == [{"type": "meditation", "start": "2026-10-20T11:00:00Z",
                                 "end": "2026-10-20T11:10:00Z", "mood": "good", "hr_avg": 58.0,
                                 "hrv_avg": 60.0}]  # fmt: skip
    assert data["rest_mode"] == {"start_date": "2026-10-18", "end_date": None}


def test_rest_periods_cuando_rango_entonces_los_que_se_solapan(client, synced):
    res = client.get("/api/v1/health/rest-periods", params={"date_from": "2026-10-01", "date_to": "2026-10-19"},
                     headers=auth(synced))  # fmt: skip
    assert res.json() == [{"start_date": "2026-10-18", "end_date": None, "source": "oura"}]
    res = client.get("/api/v1/health/rest-periods", params={"date_from": "2026-10-01", "date_to": "2026-10-10"},
                     headers=auth(synced))  # fmt: skip
    assert res.json() == []
    bad = client.get("/api/v1/health/rest-periods", params={"date_from": "2026-10-10", "date_to": "2026-10-01"},
                     headers=auth(synced))  # fmt: skip
    assert bad.status_code == 422


def test_health_cuando_otro_usuario_entonces_no_ve_datos_ajenos(client, session, synced):
    from app.models import User

    other = User(email="otro@example.com", password_hash="x")
    session.add(other)
    session.commit()
    data = client.get(f"/api/v1/health/night/{DAY}", headers=auth(other)).json()
    assert data["main"] is None and data["tags"] == []
    assert client.get(f"/api/v1/health/day/{DAY}", headers=auth(other)).json()["heartrate"] == []


# ─── Módulo apagado ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", "/api/v1/sources/oura"), ("get", "/api/v1/sources/oura/connect"), ("post", "/api/v1/sources/oura/sync"),
     ("delete", "/api/v1/sources/oura"), ("put", "/api/v1/settings/recovery-source")],
)  # fmt: skip
def test_modulo_apagado_cuando_llama_entonces_404(client, session, user, method, path):
    modules.set_user_modules(session, user, {"oura": False}, None)
    kwargs = {"json": {"source": "oura"}} if method == "put" else {}
    res = getattr(client, method)(path, headers=auth(user), **kwargs)
    assert res.status_code == 404 and res.json()["error"]["code"] == "MODULE_DISABLED"


def test_modulo_apagado_cuando_vistas_de_salud_entonces_oculta_lo_de_oura(client, session, synced):
    modules.set_user_modules(session, synced, {"oura": False}, None)
    data = client.get(f"/api/v1/health/night/{DAY}", headers=auth(synced)).json()
    assert data["source"] is None and data["tags"] == []
    assert client.get(f"/api/v1/health/day/{DAY}", headers=auth(synced)).json()["rest_mode"] is None


# ─── Sincronizar y desconectar ───────────────────────────────────────────────


def test_sync_cuando_conectado_entonces_202_y_encola(client, session, user, queued):
    assert client.post("/api/v1/sources/oura/sync", headers=auth(user)).status_code == 409
    connect(session, user)
    res = client.post("/api/v1/sources/oura/sync", headers=auth(user))
    assert res.status_code == 202 and res.json() == {"queued": True}
    assert queued == [("oura_sync_user_task", [user.id])]


def test_desconectar_cuando_sin_purge_entonces_conserva_los_datos(client, session, synced, oura):
    assert client.delete("/api/v1/sources/oura", headers=auth(synced)).status_code == 204
    session.expire_all()
    assert session.get(OuraConnection, synced.id) is None
    assert any(r.url.path == "/oauth/revoke" for r in oura.requests)
    assert session.exec(select(DailySeries)).all() and session.exec(select(Activity)).all()


def test_desconectar_cuando_purge_entonces_borra_todo_lo_de_oura(client, session, synced):
    sync_daily(session, synced.id, FakeGarmin(), days=1)  # lo del reloj se queda
    res = client.delete("/api/v1/sources/oura", params={"purge": "true"}, headers=auth(synced))
    assert res.status_code == 204
    session.expire_all()
    for model in (DailySeries, WellnessSession, HealthTag, RestPeriod):
        assert session.exec(select(model)).all() == [], model
    assert session.exec(select(Activity)).all() == []
    assert session.exec(select(DailyMetric).where(DailyMetric.day == DAY)).first() is None
    today = session.exec(select(DailyMetric).where(DailyMetric.day == date.today())).one()
    assert set(today.metric_sources.values()) == {"garmin"}


# ─── Webhooks ────────────────────────────────────────────────────────────────


def test_webhook_verificacion_cuando_token_correcto_entonces_devuelve_challenge(client, oura):
    res = client.get(WEBHOOK, params={"verification_token": "token-verificacion", "challenge": "abc"})
    assert res.status_code == 200 and res.json() == {"challenge": "abc"}


def test_webhook_verificacion_cuando_token_incorrecto_entonces_401(client, oura):
    assert client.get(WEBHOOK, params={"verification_token": "malo", "challenge": "abc"}).status_code == 401


def _post(client, event: dict, secret: str = CLIENT_SECRET, ts: str | None = None):
    body = json.dumps(event).encode()
    ts = ts or str(int(time.time()))
    sig = oura_webhooks.sign(secret, ts, body)
    return client.post(WEBHOOK, content=body, headers={"x-oura-signature": sig, "x-oura-timestamp": ts,
                                                         "content-type": "application/json"})  # fmt: skip


EVENT = {"event_type": "create", "data_type": "sleep", "object_id": "s-9", "event_time": "2026-10-20T08:00:00",
         "user_id": "oura-1"}  # fmt: skip


def test_webhook_cuando_firma_correcta_entonces_encola_el_documento(client, session, user, oura, queued):
    connect(session, user)
    res = _post(client, EVENT)
    assert res.status_code == 200
    assert queued == [("oura_fetch_object_task", [user.id, "sleep", "s-9", "create"])]


def test_webhook_cuando_firma_incorrecta_entonces_401(client, session, user, oura, queued):
    connect(session, user)
    assert _post(client, EVENT, secret="otro").status_code == 401
    assert client.post(WEBHOOK, json=EVENT).status_code == 401  # sin cabeceras
    assert queued == []


def test_webhook_cuando_timestamp_viejo_entonces_401(client, session, user, oura, queued):
    connect(session, user)
    old = str(int(time.time()) - 600)
    assert _post(client, EVENT, ts=old).status_code == 401 and queued == []


def test_webhook_cuando_usuario_desconocido_entonces_200_sin_hacer_nada(client, oura, queued):
    assert _post(client, {**EVENT, "user_id": "nadie"}).status_code == 200 and queued == []


def test_webhook_cuando_delete_entonces_encola_el_borrado(client, session, user, oura, queued):
    connect(session, user)
    _post(client, {**EVENT, "event_type": "delete", "data_type": "workout", "object_id": "w-1"})
    assert queued == [("oura_fetch_object_task", [user.id, "workout", "w-1", "delete"])]


def test_firma_cuando_timestamp_en_milisegundos_entonces_vale():
    from app.core.config import get_settings

    secret = get_settings().oura_client_secret or ""
    ts = str(int(time.time() * 1000))
    assert oura_webhooks.valid_signature(b"{}", oura_webhooks.sign(secret, ts, b"{}"), ts) is bool(secret)


# ─── Suscripciones ───────────────────────────────────────────────────────────


@pytest.fixture
def public_https(monkeypatch):
    monkeypatch.setattr(oura_webhooks, "callback_url", lambda: "https://entrenos.example.com" + WEBHOOK)


def test_suscripciones_cuando_faltan_entonces_crea_todas(session, oura, public_https):
    out = oura_webhooks.ensure_subscriptions(session)
    assert out == {"created": 48, "renewed": 0, "failed": 0}
    assert len(session.exec(select(OuraWebhookSubscription)).all()) == 48
    body = json.loads(next(r for r in oura.requests if r.method == "POST").content)
    assert body["verification_token"] == "token-verificacion" and body["callback_url"].startswith("https://")
    assert oura_webhooks.ensure_subscriptions(session) == {"created": 0, "renewed": 0, "failed": 0}


def test_suscripciones_cuando_caducan_pronto_entonces_las_renueva(session, oura, public_https):
    oura_webhooks.ensure_subscriptions(session)
    soon = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    for sub in oura.subscriptions[:5]:
        sub["expiration_time"] = soon
    assert oura_webhooks.ensure_subscriptions(session) == {"created": 0, "renewed": 5, "failed": 0}
    assert sum(1 for r in oura.requests if r.method == "PUT") == 5


def test_suscripciones_cuando_url_no_es_https_entonces_no_hace_nada(session, oura, monkeypatch):
    monkeypatch.setattr(oura_webhooks, "callback_url", lambda: "http://localhost:3000" + WEBHOOK)
    assert "https" in oura_webhooks.ensure_subscriptions(session)["skipped"]
    assert oura.requests == []


# ─── RGPD ────────────────────────────────────────────────────────────────────


def test_exportacion_cuando_hay_oura_entonces_incluye_datos_sin_tokens(session, synced):
    data = accounts.export_user_data(session, synced)
    assert data["oura_connection"][0]["oura_user_id"] == "oura-1"
    assert "access_token_enc" not in data["oura_connection"][0]
    assert "refresh_token_enc" not in data["oura_connection"][0]
    assert {s["kind"] for s in data["daily_series"]} >= {"heartrate", "hypnogram_5min"}
    assert data["wellness_sessions"] and data["health_tags"] and data["rest_periods"]
    assert "at-viejo" not in json.dumps(data, default=str)


def test_borrar_cuenta_cuando_hay_oura_entonces_no_queda_nada(session, synced):
    accounts.delete_user(session, synced)
    for model in (OuraConnection, DailySeries, WellnessSession, HealthTag, RestPeriod, DailyMetric):
        assert session.exec(select(model)).all() == [], model
