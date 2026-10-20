from datetime import UTC, datetime, timedelta
from email import message_from_bytes
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.core import email as email_core
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.core.security import create_token, hash_password
from app.models import (
    Activity,
    AuditLog,
    GarminCredential,
    PasswordReset,
    SyncRun,
    User,
    UserStatus,
)
from app.services import accounts

PASSWORD = "contraseña-de-test-123"


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access', user.token_version)}"}


def _make(session: Session, email: str, admin: bool = False, status: UserStatus = UserStatus.ACTIVE) -> User:
    u = User(email=email, password_hash=hash_password(PASSWORD), is_admin=admin, status=status)
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


@pytest.fixture
def admin(session: Session) -> User:
    return _make(session, "admin@example.com", admin=True)


@pytest.fixture
def adrian(session: Session) -> User:
    return _make(session, "adrian@example.com")


def _login(client, email: str, password: str = PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _token_from(text: str) -> str:
    return text.split("token=", 1)[1].split()[0]


# ─── Bloqueo, estados y sesiones ─────────────────────────────────────────────


def test_login_cuando_10_fallos_seguidos_entonces_bloqueo_y_admin_desbloquea(client, adrian, admin, session):
    for _ in range(accounts.LOCK_THRESHOLD):
        limiter.reset()
        assert _login(client, adrian.email, "mala-clave-000").status_code == 401
    limiter.reset()
    locked = _login(client, adrian.email)  # ni con la buena
    assert locked.status_code == 423 and "bloqueada" in locked.json()["error"]["message"]
    rows = client.get("/api/v1/admin/users", headers=auth(admin)).json()["items"]
    assert next(r for r in rows if r["email"] == adrian.email)["locked"]
    assert client.post(f"/api/v1/admin/users/{adrian.id}/unlock", headers=auth(admin)).status_code == 204
    assert _login(client, adrian.email).status_code == 200


def test_login_cuando_acierta_entonces_reinicia_fallos_y_guarda_ultimo_acceso(client, adrian, session):
    _login(client, adrian.email, "mala-clave-000")
    assert _login(client, adrian.email).status_code == 200
    session.refresh(adrian)
    assert adrian.failed_logins == 0 and adrian.last_login_at is not None


def test_desactivar_usuario_entonces_no_entra_y_sus_tokens_dejan_de_valer(client, adrian, admin, session):
    old = auth(adrian)
    res = client.patch(f"/api/v1/admin/users/{adrian.id}", json={"status": "disabled"}, headers=auth(admin))
    assert res.status_code == 200 and res.json()["status"] == "disabled"
    assert client.get("/api/v1/auth/me", headers=old).status_code == 401
    login = _login(client, adrian.email)
    assert login.status_code == 403 and "desactivada" in login.json()["error"]["message"]
    client.patch(f"/api/v1/admin/users/{adrian.id}", json={"status": "active"}, headers=auth(admin))
    assert _login(client, adrian.email).status_code == 200


def test_logout_all_entonces_access_y_refresh_antiguos_no_valen(client, adrian, session):
    login = _login(client, adrian.email)
    access = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.post("/api/v1/auth/logout-all", headers=access).status_code == 204
    assert client.get("/api/v1/auth/me", headers=access).status_code == 401
    client.cookies.set("refresh_token", create_token(adrian.id, "refresh", 0), path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_admin_cierra_sesiones_de_otro_usuario(client, adrian, admin):
    old = auth(adrian)
    assert client.post(f"/api/v1/admin/users/{adrian.id}/logout", headers=auth(admin)).status_code == 204
    assert client.get("/api/v1/auth/me", headers=old).status_code == 401


# ─── Cambiar y restablecer contraseña ────────────────────────────────────────


def test_cambiar_contraseña_cuando_actual_mal_entonces_400(client, adrian):
    body = {"current_password": "no-es-esta-0", "new_password": "una-clave-nueva-larga"}
    res = client.post("/api/v1/auth/password", json=body, headers=auth(adrian))
    assert res.status_code == 400


def test_cambiar_contraseña_entonces_tokens_nuevos_y_los_viejos_caducan(client, adrian):
    old = auth(adrian)
    body = {"current_password": PASSWORD, "new_password": "una-clave-nueva-larga"}
    res = client.post("/api/v1/auth/password", json=body, headers=old)
    assert res.status_code == 200
    assert client.get("/api/v1/auth/me", headers=old).status_code == 401
    new = {"Authorization": f"Bearer {res.json()['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=new).status_code == 200
    assert _login(client, adrian.email, "una-clave-nueva-larga").status_code == 200


def test_olvide_cuando_sin_correo_entonces_202_y_no_envia(client, adrian, outbox, session):
    res = client.post("/api/v1/auth/forgot", json={"email": adrian.email})
    assert res.status_code == 202 and outbox == []
    assert session.exec(select(PasswordReset)).first() is None


def test_olvide_cuando_email_desconocido_entonces_202_igual(client, mail_on):
    assert client.post("/api/v1/auth/forgot", json={"email": "nadie@example.com"}).status_code == 202
    assert mail_on == []


def test_restablecer_por_email_flujo_completo(client, adrian, mail_on, session):
    old = auth(adrian)
    assert client.post("/api/v1/auth/forgot", json={"email": "ADRIAN@example.com"}).status_code == 202
    assert len(mail_on) == 1 and mail_on[0]["to"] == adrian.email
    assert "/restablecer?token=" in mail_on[0]["text"] and "Restablece" in mail_on[0]["subject"]
    token = _token_from(mail_on[0]["text"])
    assert session.exec(select(PasswordReset)).one().token_hash != token  # en BD solo el hash
    assert client.get(f"/api/v1/auth/reset/check?token={token}").json() == {"email": adrian.email}
    res = client.post("/api/v1/auth/reset", json={"token": token, "password": "otra-clave-larga-1"})
    assert res.status_code == 204
    assert client.get("/api/v1/auth/me", headers=old).status_code == 401
    assert _login(client, adrian.email, "otra-clave-larga-1").status_code == 200
    reuse = client.post("/api/v1/auth/reset", json={"token": token, "password": "otra-clave-larga-2"})
    assert reuse.status_code == 400


def test_restablecer_cuando_caducado_entonces_400(client, adrian, session):
    token, _ = accounts.create_reset(session, adrian, 60)
    reset = session.exec(select(PasswordReset)).one()
    reset.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    session.add(reset)
    session.commit()
    assert client.get(f"/api/v1/auth/reset/check?token={token}").status_code == 400


def test_restablecer_cuando_bloqueado_entonces_desbloquea(client, adrian, session):
    adrian.locked_until = datetime.now(UTC) + timedelta(minutes=10)
    session.add(adrian)
    session.commit()
    token, _ = accounts.create_reset(session, adrian, 60)
    client.post("/api/v1/auth/reset", json={"token": token, "password": "otra-clave-larga-1"})
    assert _login(client, adrian.email, "otra-clave-larga-1").status_code == 200


def test_enlace_de_admin_cuando_sin_email_entonces_devuelve_enlace(client, adrian, admin, outbox):
    res = client.post(f"/api/v1/admin/users/{adrian.id}/reset-link", json={"send_email": True}, headers=auth(admin))
    body = res.json()
    assert res.status_code == 200 and "/restablecer?token=" in body["link"] and body["emailed"] is False
    assert outbox == []
    token = _token_from(body["link"])
    assert client.get(f"/api/v1/auth/reset/check?token={token}").status_code == 200


def test_enlace_de_admin_cuando_hay_correo_entonces_tambien_lo_envia(client, adrian, admin, mail_on):
    res = client.post(f"/api/v1/admin/users/{adrian.id}/reset-link", json={"send_email": True}, headers=auth(admin))
    assert res.json()["emailed"] is True and mail_on[0]["to"] == adrian.email


# ─── Registro ────────────────────────────────────────────────────────────────


def test_opciones_publicas(client, session):
    assert client.get("/api/v1/auth/options").json() == {"registration": "invite", "email_enabled": False}


def test_signup_cuando_solo_invitacion_entonces_403(client):
    res = client.post("/api/v1/auth/signup", json={"email": "x@example.com", "password": "una-clave-larga"})
    assert res.status_code == 403


def test_signup_cuando_abierto_entonces_cuenta_activa_y_sesion(client, admin):
    client.put("/api/v1/admin/settings", json={"registration_mode": "open"}, headers=auth(admin))
    res = client.post("/api/v1/auth/signup", json={"email": "Nuevo@Example.com", "password": "una-clave-larga"})
    assert res.json()["status"] == "active" and res.json()["access_token"]
    dup = client.post("/api/v1/auth/signup", json={"email": "nuevo@example.com", "password": "una-clave-larga"})
    assert dup.status_code == 409


def test_signup_con_aprobacion_entonces_pendiente_aviso_y_aprobar(client, admin, mail_on, session):
    client.put("/api/v1/admin/settings", json={"registration_mode": "approval"}, headers=auth(admin))
    res = client.post("/api/v1/auth/signup", json={"email": "adri@example.com", "password": "una-clave-larga"})
    assert res.json() == {"status": "pending", "access_token": None, "expires_in": None}
    assert [m["to"] for m in mail_on] == [admin.email] and "adri@example.com" in mail_on[0]["text"]
    login = _login(client, "adri@example.com", "una-clave-larga")
    assert login.status_code == 403 and "pendiente" in login.json()["error"]["message"]
    rows = client.get("/api/v1/admin/users", headers=auth(admin)).json()["items"]
    assert rows[0]["email"] == "adri@example.com" and rows[0]["status"] == "pending"  # pendientes primero
    pending_id = rows[0]["id"]
    assert client.post(f"/api/v1/admin/users/{pending_id}/approve", headers=auth(admin)).json()["status"] == "active"
    assert mail_on[-1]["to"] == "adri@example.com" and "lista" in mail_on[-1]["subject"]
    assert _login(client, "adri@example.com", "una-clave-larga").status_code == 200


def test_rechazar_solicitud_entonces_se_borra(client, admin, session):
    pending = _make(session, "p@example.com", status=UserStatus.PENDING)
    assert client.post(f"/api/v1/admin/users/{pending.id}/reject", headers=auth(admin)).status_code == 204
    assert session.exec(select(User).where(User.email == "p@example.com")).first() is None


# ─── Permisos de administrador ───────────────────────────────────────────────


def test_hacer_admin_a_otro_usuario_desde_el_panel(client, adrian, admin, session):
    res = client.patch(f"/api/v1/admin/users/{adrian.id}", json={"is_admin": True}, headers=auth(admin))
    assert res.json()["is_admin"] is True
    assert client.get("/api/v1/admin/users", headers=auth(adrian)).status_code == 200
    actions = [a.action for a in session.exec(select(AuditLog)).all()]
    assert "user.admin_granted" in actions


def test_quitar_el_ultimo_admin_entonces_409(client, admin):
    res = client.patch(f"/api/v1/admin/users/{admin.id}", json={"is_admin": False}, headers=auth(admin))
    assert res.status_code == 409 and "al menos un administrador" in res.json()["error"]["message"]


def test_quitarse_admin_cuando_hay_otro_entonces_ok(client, admin, session):
    other = _make(session, "otro-admin@example.com", admin=True)
    res = client.patch(f"/api/v1/admin/users/{admin.id}", json={"is_admin": False}, headers=auth(admin))
    assert res.status_code == 200 and other.is_admin


def test_desactivarse_a_si_mismo_entonces_409(client, admin):
    res = client.patch(f"/api/v1/admin/users/{admin.id}", json={"status": "disabled"}, headers=auth(admin))
    assert res.status_code == 409


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/admin/users"),
        ("get", "/api/v1/admin/invitations"),
        ("get", "/api/v1/admin/settings"),
        ("get", "/api/v1/admin/audit"),
        ("get", "/api/v1/admin/system"),
        ("post", "/api/v1/admin/users/1/logout"),
        ("delete", "/api/v1/admin/users/1?confirm=x"),
    ],
)
def test_admin_cuando_no_es_admin_entonces_403(client, adrian, method, path):
    assert getattr(client, method)(path, headers=auth(adrian)).status_code == 403


# ─── Borrado y exportación ───────────────────────────────────────────────────


def _activity(session: Session, user: User) -> None:
    session.add(Activity(user_id=user.id, sport="running", start_time=datetime.now(UTC), duration_s=1800,
                         distance_m=5000, metrics={"best_1k": 290}))  # fmt: skip
    session.commit()


def test_admin_borra_usuario_cuando_confirma_email_entonces_desaparecen_sus_datos(client, adrian, admin, session):
    _activity(session, adrian)
    uid = adrian.id
    path = f"/api/v1/admin/users/{adrian.id}"
    assert client.delete(f"{path}?confirm=otro@example.com", headers=auth(admin)).status_code == 400
    assert client.delete(f"{path}?confirm=ADRIAN@example.com", headers=auth(admin)).status_code == 204
    session.expire_all()
    assert session.get(User, uid) is None
    assert session.exec(select(Activity)).first() is None
    audit = session.exec(select(AuditLog).where(AuditLog.action == "user.deleted")).one()
    assert audit.target_email == "adrian@example.com" and audit.actor_email == admin.email


def test_admin_no_puede_borrarse_desde_el_panel(client, admin):
    res = client.delete(f"/api/v1/admin/users/{admin.id}?confirm={admin.email}", headers=auth(admin))
    assert res.status_code == 409


def test_exportar_mis_datos_entonces_json_sin_secretos(client, adrian, session):
    _activity(session, adrian)
    res = client.get("/api/v1/auth/me/export", headers=auth(adrian))
    assert res.status_code == 200 and "attachment" in res.headers["content-disposition"]
    data = res.json()
    assert data["account"]["email"] == adrian.email and len(data["activities"]) == 1
    assert "password_hash" not in res.text and "key_enc" not in res.text and "tokens_enc" not in res.text


def test_borrar_mi_cuenta_cuando_contraseña_mal_entonces_400(client, adrian):
    res = client.request("DELETE", "/api/v1/auth/me", json={"password": "no-es-0"}, headers=auth(adrian))
    assert res.status_code == 400


def test_borrar_mi_cuenta_entonces_desaparece_todo(client, adrian, session):
    _activity(session, adrian)
    uid = adrian.id
    res = client.request("DELETE", "/api/v1/auth/me", json={"password": PASSWORD}, headers=auth(adrian))
    assert res.status_code == 204
    session.expire_all()
    assert session.get(User, uid) is None and session.exec(select(Activity)).first() is None


def test_borrar_mi_cuenta_cuando_ultimo_admin_con_mas_usuarios_entonces_409(client, admin, adrian):
    res = client.request("DELETE", "/api/v1/auth/me", json={"password": PASSWORD}, headers=auth(admin))
    assert res.status_code == 409


def test_borrar_usuario_entonces_borra_sus_fit(session, adrian, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "storage_dir", str(tmp_path))
    fit = tmp_path / "fit" / str(adrian.id)
    fit.mkdir(parents=True)
    (fit / "1.zip").write_bytes(b"x")
    accounts.delete_user(session, adrian)
    assert not fit.exists()


# ─── Invitaciones, ajustes, auditoría y sistema ──────────────────────────────


def test_renovar_invitacion_entonces_enlace_nuevo_y_el_viejo_no_vale(client, admin, mail_on):
    inv = client.post("/api/v1/admin/invitations", json={"email": "r@example.com", "days": 3, "send_email": True},
                      headers=auth(admin)).json()  # fmt: skip
    assert inv["emailed"] and mail_on[0]["to"] == "r@example.com"
    renewed = client.post(f"/api/v1/admin/invitations/{inv['id']}/renew", json={"days": 10}, headers=auth(admin))
    assert renewed.json()["link"] != inv["link"]
    assert client.get(f"/api/v1/invitations/check?token={_token_from(inv['link'])}").status_code == 400
    assert client.get(f"/api/v1/invitations/check?token={_token_from(renewed.json()['link'])}").status_code == 200


def test_invitacion_caducada_aparece_como_caducada(client, admin, session):
    client.post("/api/v1/admin/invitations", json={"email": "c@example.com"}, headers=auth(admin))
    from app.models import Invitation

    inv = session.exec(select(Invitation)).one()
    inv.expires_at = datetime.now(UTC) - timedelta(days=1)
    session.add(inv)
    session.commit()
    assert client.get("/api/v1/admin/invitations", headers=auth(admin)).json()[0]["status"] == "expired"


def test_ajustes_y_auditoria(client, admin):
    res = client.put("/api/v1/admin/settings", json={"registration_mode": "approval"}, headers=auth(admin))
    assert res.json() == {"registration_mode": "approval", "email_enabled": False}
    audit = client.get("/api/v1/admin/audit", headers=auth(admin)).json()
    assert audit[0]["action"] == "settings.registration_mode"
    assert audit[0]["detail"] == {"before": "invite", "after": "approval"}


def test_lista_usuarios_con_busqueda_y_estadisticas(client, admin, adrian, session):
    _activity(session, adrian)
    session.add(SyncRun(user_id=adrian.id, status="error", error="Garmin no responde"))
    session.add(GarminCredential(user_id=adrian.id, tokens_enc="x", status="expired"))
    session.commit()
    page = client.get("/api/v1/admin/users?q=adri", headers=auth(admin)).json()
    assert page["total"] == 1
    row = page["items"][0]
    assert row["activities"] == 1 and row["garmin"] == "expired" and row["last_sync"]["status"] == "error"


def test_sistema_muestra_problemas_de_garmin_y_copias(client, admin, adrian, session, tmp_path, monkeypatch):
    session.add(SyncRun(user_id=adrian.id, status="error", error="Garmin no responde"))
    session.add(GarminCredential(user_id=adrian.id, tokens_enc="x", status="expired"))
    session.commit()
    (tmp_path / "daily-20261019.sql.gz").write_bytes(b"x" * 2048)
    monkeypatch.setattr(get_settings(), "backup_dir", str(tmp_path))
    data = client.get("/api/v1/admin/system", headers=auth(admin)).json()
    assert data["garmin_expired"] == [adrian.email]
    assert data["sync_failing"][0]["email"] == adrian.email
    assert data["last_backup"]["file"] == "daily-20261019.sql.gz" and data["last_backup"]["count"] == 1
    assert data["users_by_status"] == {"active": 2} and data["email_mode"] == "disabled"


# ─── Envío de email ──────────────────────────────────────────────────────────


def test_email_backend_fichero_guarda_eml(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "email_backend", "file")
    monkeypatch.setattr(get_settings(), "storage_dir", str(tmp_path))
    email_core.send_email(email_core.Email("a@example.com", "Hola", "texto", "<p>html</p>"))
    files = list(Path(tmp_path, "outbox").glob("*.eml"))
    message = message_from_bytes(files[0].read_bytes())
    assert message["To"] == "a@example.com" and message["Subject"] == "Hola" and message.is_multipart()


def test_email_smtp_cuando_starttls_entonces_login_y_envio(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self, context):
            calls.append(("starttls",))

        def login(self, user, password):
            calls.append(("login", user))

        def send_message(self, message):
            calls.append(("send", message["To"]))

    s = get_settings()
    for key, value in {"email_backend": "smtp", "smtp_host": "smtp.example.com", "smtp_port": 587,
                       "smtp_user": "u", "smtp_password": "p", "smtp_security": "starttls"}.items():  # fmt: skip
        monkeypatch.setattr(s, key, value)
    monkeypatch.setattr(email_core.smtplib, "SMTP", FakeSMTP)
    email_core.send_email(email_core.Email("b@example.com", "Asunto", "texto"))
    assert calls == [("connect", "smtp.example.com", 587), ("starttls",), ("login", "u"), ("send", "b@example.com")]


def test_email_desactivado_no_hace_nada(monkeypatch):
    monkeypatch.setattr(get_settings(), "email_backend", "disabled")
    email_core.send_email(email_core.Email("c@example.com", "x", "y"))  # no lanza


def test_email_html_escapa_contenido(mail_on):
    from app.services import mailer

    mailer.send_approval_request(["a@example.com"], "<script>@x.com")
    assert "<script>" not in mail_on[0]["html"] and "&lt;script&gt;" in mail_on[0]["html"]
