import json
import smtplib

import pytest
from sqlmodel import Session, select

from app.core import email as email_core
from app.core.config import get_settings
from app.core.security import create_token, hash_password
from app.models import AppSetting, User
from app.services import mailer

SMTP = {
    "enabled": True,
    "host": "smtp.gmail.com",
    "port": 587,
    "security": "starttls",
    "user": "yo@gmail.com",
    "password": "clave-de-aplicacion-1234",
    "sender": "APP ENTRENOS <yo@gmail.com>",
    "public_url": "https://entrenos.example.com/",
}


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access', user.token_version)}"}


@pytest.fixture
def admin(session: Session) -> User:
    u = User(email="admin@example.com", password_hash=hash_password("x" * 12), is_admin=True)
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


class FakeSMTP:
    sent: list = []
    fail: Exception | None = None

    def __init__(self, host, port, timeout, context=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self, context):
        pass

    def login(self, user, password):
        if FakeSMTP.fail:
            raise FakeSMTP.fail
        FakeSMTP.sent.append(("login", user, password))

    def send_message(self, message):
        FakeSMTP.sent.append(("send", message["To"], message["From"], self.host, self.port))


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch):
    FakeSMTP.sent, FakeSMTP.fail = [], None
    monkeypatch.setattr(email_core.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(email_core.smtplib, "SMTP_SSL", FakeSMTP)
    return FakeSMTP


def test_sin_panel_se_usa_el_entorno(client, admin):
    data = client.get("/api/v1/admin/email", headers=auth(admin)).json()
    assert data["source"] == "env" and data["mode"] == "disabled" and data["enabled"] is False


def test_guardar_panel_cifra_la_contraseña_y_tiene_prioridad(client, admin, session):
    res = client.put("/api/v1/admin/email", json=SMTP, headers=auth(admin))
    body = res.json()
    assert res.status_code == 200 and body["source"] == "panel" and body["mode"] == "smtp"
    assert body["has_password"] and "clave-de-aplicacion" not in res.text
    assert body["public_url"] == "https://entrenos.example.com"
    stored = json.loads(session.exec(select(AppSetting).where(AppSetting.key == "email.config")).one().value)
    assert stored["password_enc"] and "clave-de-aplicacion" not in json.dumps(stored)
    assert email_core.email_enabled() is True
    assert mailer.link("/login") == "https://entrenos.example.com/login"
    opts = client.get("/api/v1/auth/options").json()
    assert opts["email_enabled"] is True


def test_guardar_sin_contraseña_conserva_la_actual_y_vacia_la_borra(client, admin):
    client.put("/api/v1/admin/email", json=SMTP, headers=auth(admin))
    keep = client.put("/api/v1/admin/email", json={**SMTP, "password": None, "port": 465}, headers=auth(admin))
    assert keep.json()["has_password"] and keep.json()["port"] == 465
    assert email_core.current_config().password == "clave-de-aplicacion-1234"
    clear = client.put("/api/v1/admin/email", json={**SMTP, "password": ""}, headers=auth(admin))
    assert clear.json()["has_password"] is False


def test_panel_desactivado_vuelve_al_entorno(client, admin):
    client.put("/api/v1/admin/email", json={**SMTP, "enabled": False}, headers=auth(admin))
    assert client.get("/api/v1/admin/email", headers=auth(admin)).json()["source"] == "env"
    assert email_core.email_enabled() is False


def test_borrar_panel(client, admin):
    client.put("/api/v1/admin/email", json=SMTP, headers=auth(admin))
    assert client.delete("/api/v1/admin/email", headers=auth(admin)).status_code == 204
    assert client.get("/api/v1/admin/email", headers=auth(admin)).json()["source"] == "env"


def test_email_de_prueba_ok_usa_los_datos_del_panel(client, admin, fake_smtp):
    client.put("/api/v1/admin/email", json=SMTP, headers=auth(admin))
    res = client.post("/api/v1/admin/email/test", json={}, headers=auth(admin))
    assert res.status_code == 200 and "admin@example.com" in res.json()["message"]
    assert ("login", "yo@gmail.com", "clave-de-aplicacion-1234") in fake_smtp.sent
    assert ("send", "admin@example.com", "APP ENTRENOS <yo@gmail.com>", "smtp.gmail.com", 587) in fake_smtp.sent


def test_email_de_prueba_con_credenciales_malas_explica_el_motivo(client, admin, fake_smtp):
    client.put("/api/v1/admin/email", json=SMTP, headers=auth(admin))
    fake_smtp.fail = smtplib.SMTPAuthenticationError(535, b"bad credentials")
    res = client.post("/api/v1/admin/email/test", json={}, headers=auth(admin))
    assert res.status_code == 400 and "contraseña de aplicación" in res.json()["error"]["message"]


def test_email_de_prueba_sin_configuracion_400(client, admin):
    assert client.post("/api/v1/admin/email/test", json={}, headers=auth(admin)).status_code == 400


def test_email_de_prueba_en_modo_fichero(client, admin, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "email_backend", "file")
    monkeypatch.setattr(get_settings(), "storage_dir", str(tmp_path))
    res = client.post("/api/v1/admin/email/test", json={"to": "otro@example.com"}, headers=auth(admin))
    assert "bandeja local" in res.json()["message"] and list((tmp_path / "outbox").glob("*.eml"))


def test_no_admin_no_ve_el_correo(client, session):
    user = User(email="u@example.com", password_hash="x")
    session.add(user)
    session.commit()
    assert client.get("/api/v1/admin/email", headers=auth(user)).status_code == 403


@pytest.mark.parametrize(
    ("exc", "fragment"),
    [
        (smtplib.SMTPSenderRefused(553, b"no", "x@y.com"), "remitente"),
        (smtplib.SMTPConnectError(421, b"no"), "conectar"),
        (TimeoutError(), "no respondió"),
        (OSError("dns"), "nombre del servidor"),
    ],
)
def test_textos_de_error_smtp(exc, fragment):
    assert fragment in email_core.smtp_error_text(exc)
