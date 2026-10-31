"""Módulos activables por el administrador: API cortada con 404, tareas que no hacen nada y caché."""

import json

import pytest
import redis
from sqlmodel import Session, select

from app.core.security import create_token, hash_password
from app.models import AppSetting, AuditLog, User
from app.services import modules

PASSWORD = "contraseña-de-test-123"


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access', user.token_version)}"}


@pytest.fixture
def admin(session: Session) -> User:
    u = User(email="admin@example.com", password_hash=hash_password(PASSWORD), is_admin=True)
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _off(session: Session, *names: str) -> None:
    modules.set_modules(session, dict.fromkeys(names, False), None)


# ─── Servicio y caché ────────────────────────────────────────────────────────


def test_modulos_cuando_nada_guardado_entonces_valores_por_defecto(session):
    assert modules.all_modules(session) == {
        "entrenadores": False, "ia": True, "reloj": True, "rutas": True, "nutricion": False, "oura": True,
        "suunto": True, "zepp": True, "xiaomi": True}  # fmt: skip
    assert modules.enabled(session, "ia") and not modules.enabled(session, "nutricion")
    assert not modules.enabled(session, "inventado")


def test_set_modules_cuando_nombre_desconocido_entonces_error(session):
    with pytest.raises(ValueError, match="desconocido"):
        modules.set_modules(session, {"teletransporte": True}, None)


def test_set_modules_cuando_guarda_entonces_invalida_la_cache(session):
    assert modules.enabled(session, "ia")  # se cachea «activado»
    _off(session, "ia")
    assert not modules.enabled(session, "ia")  # sin esperar los 30 s
    stored = json.loads(session.get(AppSetting, modules.SETTING_KEY).value)
    assert stored["ia"] is False and stored["reloj"] is True


class MemoryRedis:
    """Redis en memoria: la CI no tiene Redis y sin él no hay caché que probar."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get(self, key):
        return self.data.get(key)

    def setex(self, key, _ttl, value):
        self.data[key] = value

    def delete(self, key):
        self.data.pop(key, None)


def test_modulos_cuando_cambia_la_bd_por_fuera_entonces_se_sirve_la_cache(session, monkeypatch):
    fake = MemoryRedis()
    monkeypatch.setattr(modules, "_redis", lambda: fake)
    assert modules.enabled(session, "rutas")
    session.add(AppSetting(key=modules.SETTING_KEY, value=json.dumps({"rutas": False})))
    session.commit()
    assert modules.enabled(session, "rutas")  # sigue en caché
    modules.invalidate_cache()
    assert not modules.enabled(session, "rutas")


def test_modulos_cuando_redis_falla_entonces_lee_de_bd(session, monkeypatch):
    class Broken:
        def get(self, *_):
            raise redis.ConnectionError("caído")

        def setex(self, *_):
            raise redis.ConnectionError("caído")

        def delete(self, *_):
            raise redis.ConnectionError("caído")

    monkeypatch.setattr(modules, "_redis", lambda: Broken())
    _off(session, "reloj")
    assert not modules.enabled(session, "reloj") and modules.enabled(session, "ia")


def test_modulos_cuando_json_roto_entonces_valores_por_defecto(session):
    session.add(AppSetting(key=modules.SETTING_KEY, value="{roto"))
    session.commit()
    assert modules.all_modules(session) == modules.DEFAULTS


# ─── Endpoints ───────────────────────────────────────────────────────────────


def test_get_modules_cuando_logueado_entonces_estado(client, user):
    assert client.get("/api/v1/app/modules").status_code == 401
    res = client.get("/api/v1/app/modules", headers=auth(user))
    assert res.status_code == 200 and res.json()["ia"] is True and res.json()["entrenadores"] is False


def test_put_modules_cuando_no_admin_entonces_403(client, user, session):
    res = client.put("/api/v1/admin/modules", json={"ia": False}, headers=auth(user))
    assert res.status_code == 403
    assert modules.enabled(session, "ia")


def test_put_modules_cuando_admin_entonces_guarda_y_audita(client, admin, session):
    res = client.put("/api/v1/admin/modules", json={"ia": False, "nutricion": True}, headers=auth(admin))
    assert res.status_code == 200
    assert res.json() == {
        "entrenadores": False, "ia": False, "reloj": True, "rutas": True, "nutricion": True, "oura": True,
        "suunto": True, "zepp": True, "xiaomi": True}  # fmt: skip
    assert client.get("/api/v1/app/modules", headers=auth(admin)).json()["ia"] is False
    log = session.exec(select(AuditLog).where(AuditLog.action == "settings.modules")).one()
    assert log.actor_id == admin.id and log.detail == {"ia": "desactivado", "nutricion": "activado"}
    # Repetir lo mismo no añade otra entrada de auditoría.
    client.put("/api/v1/admin/modules", json={"ia": False}, headers=auth(admin))
    assert len(session.exec(select(AuditLog).where(AuditLog.action == "settings.modules")).all()) == 1


@pytest.mark.parametrize(
    ("module", "method", "path"),
    [
        ("ia", "get", "/api/v1/ai/providers"),
        ("ia", "get", "/api/v1/chat/conversations"),
        ("ia", "get", "/api/v1/coach/memories"),
        ("ia", "get", "/api/v1/coach/checkin"),
        ("ia", "get", "/api/v1/ai/review-settings"),
        ("ia", "get", "/api/v1/ai/reviews/latest"),
        ("reloj", "get", "/api/v1/workouts/settings"),
        ("reloj", "post", "/api/v1/workouts/send-upcoming"),
        ("reloj", "post", "/api/v1/plans/1/garmin"),
        ("reloj", "delete", "/api/v1/plans/1/garmin"),
        ("reloj", "post", "/api/v1/plans/1/coros"),
        ("rutas", "get", "/api/v1/planned-routes"),
        ("rutas", "put", "/api/v1/plans/1/route"),
    ],
)
def test_api_cuando_modulo_apagado_entonces_404_module_disabled(client, user, session, module, method, path):
    _off(session, module)
    res = client.request(method, path, headers=auth(user), json={})
    assert res.status_code == 404
    body = res.json()["error"]
    assert body["code"] == "MODULE_DISABLED" and "desactivado" in body["message"]


def test_api_cuando_modulo_apagado_y_anonimo_entonces_401(client, session):
    _off(session, "ia")
    assert client.get("/api/v1/coach/memories").status_code == 401


def test_api_cuando_reloj_apagado_entonces_fit_sigue_y_otros_modulos_tambien(client, user, session):
    _off(session, "reloj")
    assert client.get("/api/v1/coach/memories", headers=auth(user)).status_code == 200
    assert client.get("/api/v1/planned-routes", headers=auth(user)).status_code == 200


# ─── Tareas en segundo plano ─────────────────────────────────────────────────


def _review_and_checkin(session, user):
    from datetime import UTC, date, datetime

    from app.models import Activity, ActivityReview, WeeklyCheckin

    activity = Activity(user_id=user.id, sport="running", start_time=datetime.now(UTC), duration_s=3600)
    session.add(activity)
    session.commit()
    review = ActivityReview(activity_id=activity.id, user_id=user.id)
    checkin = WeeklyCheckin(user_id=user.id, week_start=date(2026, 10, 19))
    session.add_all([review, checkin])
    session.commit()
    return review.id, checkin.id


def test_tareas_ia_cuando_apagado_entonces_no_hacen_nada(session, user, monkeypatch):
    from app.tasks import ai as ai_tasks
    from app.tasks import coach as coach_tasks

    review_id, checkin_id = _review_and_checkin(session, user)
    called: list = []
    monkeypatch.setattr(ai_tasks, "generate", lambda *a: called.append("review"))
    monkeypatch.setattr(coach_tasks.weekly_review, "generate", lambda *a: called.append("summary"))
    _off(session, "ia")
    assert ai_tasks.review_activity_task(review_id) == "módulo desactivado"
    assert coach_tasks.weekly_summary_task(checkin_id) == "módulo desactivado"
    assert called == []


def test_revision_semanal_cuando_ia_apagada_para_la_cuenta_entonces_no_se_abre(session, user, monkeypatch):
    from datetime import UTC, datetime

    from app.models import AiProviderConfig
    from app.services import weekly_review

    session.add(AiProviderConfig(user_id=user.id, provider="gemini", key_enc="x", key_last4="1234", model="m"))
    session.commit()
    opened: list = []
    monkeypatch.setattr(weekly_review, "open_week", lambda *a, **k: opened.append(a[1]))
    modules.set_user_modules(session, user, {"ia": False}, None)
    sunday = datetime(2026, 10, 25, 20, tzinfo=UTC)
    assert weekly_review.due_tick(session, sunday) == 0
    modules.set_user_modules(session, user, {"ia": None}, None)
    assert weekly_review.due_tick(session, sunday) == 1 and opened == [user.id]


# ─── Módulos por cuenta ──────────────────────────────────────────────────────


def test_modulos_cuando_la_cuenta_tiene_valor_propio_entonces_manda_sobre_el_general(session, user):
    _off(session, "ia")
    modules.set_user_modules(session, user, {"ia": True, "rutas": False}, None)
    mine = modules.for_user(session, user.id)
    assert mine["ia"] is True and mine["rutas"] is False and mine["reloj"] is True
    assert modules.all_modules(session)["ia"] is False  # el general no cambia
    modules.set_user_modules(session, user, {"ia": None}, None)  # vuelve al general
    assert not modules.enabled(session, "ia", user.id)


def test_modulos_cuando_nombre_desconocido_en_la_cuenta_entonces_error(session, user):
    with pytest.raises(ValueError, match="desconocido"):
        modules.set_user_modules(session, user, {"teletransporte": True}, None)


def test_api_cuando_ia_apagada_solo_para_una_cuenta_entonces_solo_ella_recibe_404(client, user, admin, session):
    modules.set_user_modules(session, user, {"ia": False}, admin)
    r = client.get("/api/v1/ai/providers", headers=auth(user))
    assert r.status_code == 404 and r.json()["error"]["code"] == "MODULE_DISABLED"
    assert client.get("/api/v1/ai/providers", headers=auth(admin)).status_code == 200
    assert client.get("/api/v1/app/modules", headers=auth(user)).json()["ia"] is False
    assert client.get("/api/v1/app/modules", headers=auth(admin)).json()["ia"] is True


def test_admin_cuando_fija_modulos_de_una_cuenta_entonces_guarda_lista_y_audita(client, user, admin, session):
    r = client.patch(f"/api/v1/admin/users/{user.id}", headers=auth(admin),
                     json={"modules": {"entrenadores": True, "reloj": False}})  # fmt: skip
    assert r.status_code == 200 and r.json()["modules"] == {"entrenadores": True, "reloj": False}
    r = client.patch(f"/api/v1/admin/users/{user.id}", headers=auth(admin), json={"modules": {"reloj": None}})
    assert r.json()["modules"] == {"entrenadores": True}
    rows = session.exec(select(AuditLog).where(AuditLog.action == "user.modules")).all()
    assert len(rows) == 2
    bad = client.patch(f"/api/v1/admin/users/{user.id}", headers=auth(admin), json={"modules": {"x": True}})
    assert bad.status_code == 422
    assert client.patch(f"/api/v1/admin/users/{user.id}", headers=auth(user),
                        json={"modules": {"ia": True}}).status_code == 403  # fmt: skip


def test_admin_cuando_pide_el_valor_general_entonces_no_le_afecta_el_suyo(client, admin, session):
    modules.set_user_modules(session, admin, {"rutas": False}, admin)
    assert client.get("/api/v1/admin/modules", headers=auth(admin)).json()["rutas"] is True


def test_tareas_reloj_cuando_apagado_solo_para_una_cuenta_entonces_las_demas_siguen(session, user, monkeypatch):
    from app.tasks import workouts as tasks

    modules.set_user_modules(session, user, {"reloj": False}, None)
    monkeypatch.setattr(tasks, "GarminConnectClient", lambda *a: (_ for _ in ()).throw(AssertionError))
    assert tasks.send_workouts_task(user.id) == {}


def test_analisis_automatico_cuando_ia_apagada_entonces_no_se_encola(session, user):
    from datetime import UTC, datetime

    from app.models import Activity
    from app.services import activity_review

    activity = Activity(user_id=user.id, sport="running", start_time=datetime.now(UTC), duration_s=3600)
    session.add(activity)
    session.commit()
    _off(session, "ia")
    assert activity_review.skip_reason(session, activity) == "módulo desactivado"


def test_tareas_reloj_cuando_apagado_entonces_no_hacen_nada(session, user, monkeypatch):
    from app.tasks import workouts as tasks

    called: list = []
    monkeypatch.setattr(tasks, "GarminConnectClient", lambda *a: called.append("client"))
    monkeypatch.setattr(tasks.send_workouts_task, "apply_async", lambda **kw: called.append("queued"))
    _off(session, "reloj")
    assert tasks.send_workouts_task(user.id) == {}
    assert tasks.delete_workout_task(user.id, 5) is None
    assert tasks.send_workouts_all_task() == 0
    assert called == []


def test_queue_send_cuando_reloj_apagado_entonces_no_encola(session, user, monkeypatch):
    from app.api import workouts as api
    from app.models import GarminCredential, UserSettings
    from app.tasks import workouts as tasks

    sent: list = []
    monkeypatch.setattr(tasks.send_workouts_task, "apply_async", lambda **kw: sent.append(kw["args"]))
    session.add(UserSettings(user_id=user.id, garmin_workouts_auto=True))
    session.add(GarminCredential(user_id=user.id, tokens_enc="x"))
    session.commit()
    _off(session, "reloj")
    api.queue_send(session, user.id)
    assert sent == []


def test_desactivar_no_borra_datos(client, user, session):
    from app.models import ChatConversation

    session.add(ChatConversation(user_id=user.id, title="Hola"))
    session.commit()
    _off(session, "ia")
    modules.set_modules(session, {"ia": True}, None)
    assert len(client.get("/api/v1/chat/conversations", headers=auth(user)).json()) == 1
