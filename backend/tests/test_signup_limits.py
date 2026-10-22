from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.security import create_token, hash_password
from app.models import AccountTier, AuditLog, EmailVerification, PlannedSession, RaceGoal, User, UserStatus
from app.services import accounts, limits, signup_guard
from app.services.sync_service import sync_activities

PASSWORD = "una-clave-larga-1"


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access', user.token_version)}"}


def _make(session: Session, email: str, **kwargs) -> User:
    u = User(email=email, password_hash=hash_password(PASSWORD), **kwargs)
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _token(text: str) -> str:
    return text.split("token=", 1)[1].split()[0]


@pytest.fixture
def admin(session: Session) -> User:
    return _make(session, "admin@example.com", is_admin=True)


@pytest.fixture
def open_signup(client, admin, mail_on) -> list[dict]:
    """Registro abierto con correo (backend de fichero); devuelve la bandeja."""
    client.put("/api/v1/admin/settings", json={"registration_mode": "open"}, headers=auth(admin))
    return mail_on


def _signup(client, email: str = "nuevo@example.com", **extra):
    return client.post("/api/v1/auth/signup", json={"email": email, "password": PASSWORD, **extra})


# ─── Confirmar email ─────────────────────────────────────────────────────────


def test_signup_abierto_entonces_cuenta_basica_sin_confirmar_y_email(client, open_signup, session):
    res = _signup(client, "Nuevo@Example.com")
    assert res.status_code == 202 and res.json()["status"] == "unverified"
    user = session.exec(select(User).where(User.email == "nuevo@example.com")).one()
    assert user.status == UserStatus.UNVERIFIED and user.tier == AccountTier.BASIC
    assert open_signup[-1]["to"] == "nuevo@example.com" and "Confirma" in open_signup[-1]["subject"]
    assert _signup(client, "nuevo@example.com").status_code == 409


def test_login_sin_confirmar_entonces_403_con_codigo_y_reenvio(client, open_signup):
    _signup(client)
    login = client.post("/api/v1/auth/login", json={"email": "nuevo@example.com", "password": PASSWORD})
    assert login.status_code == 403 and login.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"
    sent = len(open_signup)
    assert client.post("/api/v1/auth/verify/resend", json={"email": "nuevo@example.com"}).status_code == 202
    assert len(open_signup) == sent + 1
    assert client.post("/api/v1/auth/verify/resend", json={"email": "nadie@example.com"}).status_code == 202
    assert len(open_signup) == sent + 1  # mismo mensaje, sin envío


def test_verificar_entonces_activa_inicia_sesion_y_un_solo_uso(client, open_signup, session):
    _signup(client)
    token = _token(open_signup[-1]["text"])
    res = client.post("/api/v1/auth/verify", json={"token": token})
    assert res.json()["status"] == "active" and res.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {res.json()['access_token']}"}).json()
    assert me["tier"] == "basic" and me["limits"]["max_goals"] == limits.DEFAULTS["basic_max_goals"]
    assert client.post("/api/v1/auth/verify", json={"token": token}).status_code == 400


def test_verificar_cuando_caducado_entonces_400(client, open_signup, session):
    _signup(client)
    row = session.exec(select(EmailVerification)).one()
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    session.add(row)
    session.commit()
    assert client.post("/api/v1/auth/verify", json={"token": _token(open_signup[-1]["text"])}).status_code == 400


def test_signup_sin_correo_entonces_no_disponible(client, admin):
    client.put("/api/v1/admin/settings", json={"registration_mode": "open"}, headers=auth(admin))
    options = client.get("/api/v1/auth/options").json()
    assert options["registration"] == "open" and options["signup_available"] is False
    assert _signup(client).status_code == 403


# ─── Captcha y emails desechables ────────────────────────────────────────────


def test_signup_cuando_email_desechable_entonces_422(client, open_signup):
    for email in ("x@mailinator.com", "x@sub.yopmail.com"):
        res = _signup(client, email)
        assert res.status_code == 422 and "permanente" in res.json()["error"]["message"]


def test_dominios_extra_del_admin_bloquean(client, open_signup, admin):
    res = client.put("/api/v1/admin/settings", json={"blocked_domains": ["@Empresa-Rara.com, otro.org"]},
                     headers=auth(admin))  # fmt: skip
    assert res.json()["blocked_domains"] == ["empresa-rara.com", "otro.org"]
    assert _signup(client, "x@empresa-rara.com").status_code == 422
    assert _signup(client, "x@gmail.com").status_code == 202


def test_captcha_cuando_activado_y_falla_entonces_400(client, open_signup, monkeypatch):
    monkeypatch.setattr(get_settings(), "turnstile_site_key", "site")
    monkeypatch.setattr(get_settings(), "turnstile_secret_key", "secret")
    monkeypatch.setattr("app.api.auth.verify_captcha", lambda token, ip: token == "ok")
    assert client.get("/api/v1/auth/options").json()["captcha_site_key"] == "site"
    assert _signup(client, captcha_token="mal").status_code == 400
    assert _signup(client, captcha_token="ok").status_code == 202


def test_verify_captcha_con_cloudflare_simulado(monkeypatch):
    monkeypatch.setattr(get_settings(), "turnstile_site_key", "site")
    monkeypatch.setattr(get_settings(), "turnstile_secret_key", "secret")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"success": "response=ok" in seen["body"]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert signup_guard.verify_captcha("ok", "1.2.3.4", client=client) is True
    assert "secret=secret" in seen["body"] and "remoteip=1.2.3.4" in seen["body"]
    assert signup_guard.verify_captcha("mal", None, client=client) is False
    assert signup_guard.verify_captcha(None, None, client=client) is False
    down = httpx.Client(transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("x"))))
    assert signup_guard.verify_captcha("ok", None, client=down) is False


def test_verify_captcha_sin_configurar_entonces_pasa():
    assert signup_guard.verify_captcha(None, None) is True


# ─── Niveles y cuotas ────────────────────────────────────────────────────────


@pytest.fixture
def basic(session: Session) -> User:
    return _make(session, "basica@example.com", tier=AccountTier.BASIC)


def _goal(day: date) -> dict:
    return {"name": "Carrera", "race_date": day.isoformat(), "distance_m": 10000, "target_time_s": None}


def test_cuota_de_objetivos_basica_y_completa_sin_limite(client, basic, session, admin):
    future = date.today() + timedelta(days=30)
    for _ in range(limits.DEFAULTS["basic_max_goals"]):
        assert client.post("/api/v1/goals", json=_goal(future), headers=auth(basic)).status_code == 201
    over = client.post("/api/v1/goals", json=_goal(future), headers=auth(basic))
    assert over.status_code == 409 and "Básica" in over.json()["error"]["message"]
    # Los pasados no cuentan como activos.
    session.add(RaceGoal(user_id=basic.id, name="Vieja", race_date=date.today() - timedelta(days=5), distance_m=5000))
    session.commit()
    for _ in range(5):
        assert client.post("/api/v1/goals", json=_goal(future), headers=auth(admin)).status_code == 201


def _session_body(day: date) -> dict:
    return {"day": day.isoformat(), "sport": "running", "title": "Rodaje", "blocks": []}


def test_cuota_de_sesiones_por_semana_al_crear_y_al_mover(client, basic, admin):
    put = client.put("/api/v1/admin/settings", json={"limits": {"basic_history_days": 180, "basic_max_goals": 2,
                     "basic_max_sessions_week": 2}}, headers=auth(admin))  # fmt: skip
    assert put.json()["limits"]["basic_max_sessions_week"] == 2
    monday = date.today() - timedelta(days=date.today().weekday()) + timedelta(days=14)
    ids = [client.post("/api/v1/plans", json=_session_body(monday), headers=auth(basic)).json()["id"]
           for _ in range(2)]  # fmt: skip
    assert client.post("/api/v1/plans", json=_session_body(monday), headers=auth(basic)).status_code == 409
    other_week = client.post("/api/v1/plans", json=_session_body(monday + timedelta(days=7)), headers=auth(basic))
    assert other_week.status_code == 201
    # Mover dentro de la misma semana sí; a la semana llena, no.
    same = client.put(f"/api/v1/plans/{ids[0]}", json=_session_body(monday + timedelta(days=2)), headers=auth(basic))
    assert same.status_code == 200
    moved = client.put(f"/api/v1/plans/{other_week.json()['id']}", json=_session_body(monday), headers=auth(basic))
    assert moved.status_code == 409


def test_admin_cambia_nivel_y_queda_auditado(client, basic, admin, session):
    res = client.patch(f"/api/v1/admin/users/{basic.id}", json={"tier": "full"}, headers=auth(admin))
    assert res.json()["tier"] == "full"
    assert session.exec(select(AuditLog).where(AuditLog.action == "user.tier_full")).one()
    me = client.get("/api/v1/auth/me", headers=auth(basic)).json()
    assert me["limits"] == {"history_days": None, "max_goals": None, "max_sessions_week": None}


def test_limites_se_acotan_al_guardar(session):
    changed = limits.save_basic_limits(session, basic_history_days=5, basic_max_goals=999, basic_max_sessions_week=14)
    session.commit()
    lim = limits.basic_limits(session)
    assert (lim.history_days, lim.max_goals) == (30, 50) and "basic_max_sessions_week" not in changed


def test_invitado_entra_como_completo(client, admin):
    inv = client.post("/api/v1/admin/invitations", json={"email": "inv@example.com"}, headers=auth(admin)).json()
    res = client.post("/api/v1/auth/register", json={"token": _token(inv["link"]), "password": PASSWORD})
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {res.json()['access_token']}"}).json()
    assert me["tier"] == "full"


# ─── Histórico limitado en la sincronización ─────────────────────────────────


class _Source:
    def __init__(self, days_ago: list[int]):
        self.items = [
            {"activityId": 1000 + i, "startTimeGMT": f"{date.today() - timedelta(days=d)} 08:00:00"}
            for i, d in enumerate(days_ago)
        ]
        self.pages = 0

    def get_devices(self):
        return []

    def get_activities(self, start, limit):
        self.pages += 1
        return self.items[start : start + limit]


def test_sync_con_since_se_detiene_en_la_fecha(monkeypatch, session, basic):
    imported = []
    monkeypatch.setattr("app.services.sync_service.import_activity",
                        lambda s, uid, src, st, summary, names: imported.append(summary["activityId"]))  # fmt: skip
    source = _Source([1, 10, 100, 200, 400])
    n = sync_activities(session, basic.id, source, storage=None, max_new=None, since=date.today() - timedelta(days=180))
    assert n == 3 and imported == [1000, 1001, 1002]


def test_history_since_segun_nivel(session, basic, admin):
    today = date(2026, 10, 22)
    assert limits.history_since(session, basic, today) == today - timedelta(days=180)
    assert limits.history_since(session, admin, today) is None


# ─── Mantenimiento diario ────────────────────────────────────────────────────


def test_housekeeping_borra_no_confirmadas_de_mas_de_48h(session):
    old = _make(session, "vieja@example.com", status=UserStatus.UNVERIFIED, tier=AccountTier.BASIC)
    old.created_at = datetime.now(UTC) - timedelta(hours=49)
    session.add(old)
    fresh = _make(session, "nueva@example.com", status=UserStatus.UNVERIFIED, tier=AccountTier.BASIC)
    session.commit()
    fresh_id = fresh.id
    result = accounts.housekeeping(session, email_on=False, warn=lambda e, d: None)
    assert result["unverified_deleted"] == 1
    assert session.get(User, fresh_id) is not None


def test_housekeeping_avisa_borra_y_entrar_cancela(session, client, admin):
    now = datetime.now(UTC)
    idle = _make(session, "idle@example.com", tier=AccountTier.BASIC, last_login_at=now - timedelta(days=200))
    back = _make(session, "vuelve@example.com", tier=AccountTier.BASIC, last_login_at=now - timedelta(days=200))
    full = _make(session, "full@example.com", last_login_at=now - timedelta(days=400))
    warned = []
    result = accounts.housekeeping(session, email_on=True, warn=lambda e, d: warned.append(e), at=now)
    assert result["warned"] == 2 and sorted(warned) == ["idle@example.com", "vuelve@example.com"]
    # Uno vuelve a entrar: se cancela su aviso.
    assert client.post("/api/v1/auth/login", json={"email": back.email, "password": PASSWORD}).status_code == 200
    later = now + timedelta(days=accounts.INACTIVE_DELETE_DAYS + 1)
    idle_id, back_id, full_id = idle.id, back.id, full.id
    result = accounts.housekeeping(session, email_on=True, warn=lambda e, d: None, at=later)
    session.expire_all()
    assert result["inactive_deleted"] == 1 and session.get(User, idle_id) is None
    assert session.get(User, back_id) is not None and session.get(User, full_id) is not None
    assert session.exec(select(AuditLog).where(AuditLog.action == "user.inactive_deleted")).one().actor_id is None


def test_housekeeping_sin_correo_no_avisa_ni_borra_inactivas(session):
    _make(session, "idle@example.com", tier=AccountTier.BASIC,
          last_login_at=datetime.now(UTC) - timedelta(days=400))  # fmt: skip
    result = accounts.housekeeping(session, email_on=False, warn=lambda e, d: None)
    assert result == {"unverified_deleted": 0, "warned": 0, "inactive_deleted": 0}


def test_sistema_cuenta_avisadas(client, admin, session):
    _make(session, "a@example.com", tier=AccountTier.BASIC,
          inactivity_warned_at=datetime.now(UTC) - timedelta(days=25))  # fmt: skip
    data = client.get("/api/v1/admin/system", headers=auth(admin)).json()
    assert data["inactive_warned"] == 1 and data["inactive_deleting_7d"] == 1


def test_plantillas_de_email_nuevas(mail_on):
    from app.services import mailer

    assert mailer.send_email_verification("a@example.com", "t" * 30, 24)
    mailer.send_inactivity_warning("b@example.com", 30)
    assert "/verificar?token=" in mail_on[0]["text"] and "30 días" in mail_on[1]["text"]


def test_planned_session_model_sigue_igual():
    # Salvaguarda: la cuota cuenta filas de PlannedSession por usuario y día.
    assert {"user_id", "day"} <= set(PlannedSession.model_fields)


# ─── Configuración guiada ────────────────────────────────────────────────────


def test_configuracion_guiada_cuenta_nueva_pendiente_y_se_marca(client, session):
    user = _make(session, "nueva@example.com")
    assert client.get("/api/v1/auth/me", headers=auth(user)).json()["onboarded"] is False
    res = client.put("/api/v1/auth/me/onboarding", json={"done": True}, headers=auth(user))
    assert res.status_code == 204
    assert client.get("/api/v1/auth/me", headers=auth(user)).json()["onboarded"] is True
    client.put("/api/v1/auth/me/onboarding", json={"done": False}, headers=auth(user))  # repetir desde Ajustes
    assert client.get("/api/v1/auth/me", headers=auth(user)).json()["onboarded"] is False
