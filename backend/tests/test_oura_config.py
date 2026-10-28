"""Credenciales de la app de Oura desde el panel de administración (cifradas, con el entorno de respaldo)."""

import pytest
from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.security import create_token, hash_password
from app.models import AppSetting, AuditLog, User
from app.services import oura_config


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access', user.token_version)}"}


@pytest.fixture
def admin(session: Session) -> User:
    u = User(email="admin-oura@example.com", password_hash=hash_password("contraseña-de-test-123"), is_admin=True)
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


@pytest.fixture(autouse=True)
def _sin_entorno(monkeypatch):
    for key in ("oura_client_id", "oura_client_secret", "oura_webhook_token"):
        monkeypatch.setattr(get_settings(), key, "")


def test_credenciales_cuando_nada_configurado_entonces_no_configurado(session):
    creds = oura_config.credentials(session)
    assert not creds.configured and creds.source is None


def test_credenciales_cuando_solo_entorno_entonces_usa_entorno(session, monkeypatch):
    monkeypatch.setattr(get_settings(), "oura_client_id", "id-env")
    monkeypatch.setattr(get_settings(), "oura_client_secret", "secret-env")
    creds = oura_config.credentials(session)
    assert creds.configured and creds.source == "entorno" and creds.client_id == "id-env"


def test_guardar_cuando_panel_entonces_cifra_y_manda_sobre_el_entorno(session, admin, monkeypatch):
    monkeypatch.setattr(get_settings(), "oura_client_id", "id-env")
    monkeypatch.setattr(get_settings(), "oura_client_secret", "secret-env")
    creds = oura_config.save(session, admin, client_id="id-panel", client_secret="secreto-panel")
    assert creds.source == "panel" and creds.client_id == "id-panel" and creds.client_secret == "secreto-panel"
    assert creds.webhook_token  # se genera solo
    stored = session.get(AppSetting, oura_config.KEY_SECRET).value
    assert "secreto-panel" not in stored  # cifrado
    assert session.exec(select(AuditLog).where(AuditLog.action == "settings.oura")).first() is not None


def test_guardar_cuando_secreto_vacio_entonces_conserva_el_anterior_y_el_token(session, admin):
    first = oura_config.save(session, admin, client_id="id", client_secret="uno")
    second = oura_config.save(session, admin, client_id="id-2", client_secret="")
    assert second.client_secret == "uno" and second.client_id == "id-2"
    assert second.webhook_token == first.webhook_token
    third = oura_config.save(session, admin, client_id="id-2", client_secret=None, new_webhook_token=True)
    assert third.webhook_token != first.webhook_token


def test_guardar_cuando_falta_secreto_la_primera_vez_entonces_error(session, admin):
    with pytest.raises(ValueError, match="Client Secret"):
        oura_config.save(session, admin, client_id="id", client_secret="")


def test_quitar_cuando_habia_panel_entonces_vuelve_al_entorno(session, admin, monkeypatch):
    oura_config.save(session, admin, client_id="id", client_secret="s")
    monkeypatch.setattr(get_settings(), "oura_client_id", "id-env")
    monkeypatch.setattr(get_settings(), "oura_client_secret", "secret-env")
    oura_config.clear(session, admin)
    assert oura_config.credentials(session).source == "entorno"


def test_api_cuando_admin_entonces_guarda_y_nunca_devuelve_el_secreto(client, admin):
    r = client.put("/api/v1/admin/oura", headers=auth(admin), json={"client_id": "abc", "client_secret": "xyz"})
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] and body["has_secret"] and body["has_webhook_token"] and body["source"] == "panel"
    assert "xyz" not in r.text
    assert any(u.endswith("/api/v1/sources/oura/callback") for u in body["redirect_uris"])
    assert client.get("/api/v1/admin/oura", headers=auth(admin)).json()["client_id"] == "abc"
    assert client.delete("/api/v1/admin/oura", headers=auth(admin)).status_code == 204
    assert not client.get("/api/v1/admin/oura", headers=auth(admin)).json()["configured"]


def test_api_cuando_no_admin_entonces_403(client, user):
    assert client.get("/api/v1/admin/oura", headers=auth(user)).status_code == 403
    assert client.put("/api/v1/admin/oura", headers=auth(user), json={"client_id": "a"}).status_code == 403


def test_estado_de_oura_cuando_configurado_en_el_panel_entonces_lo_ve_el_usuario(client, admin, user, session):
    oura_config.save(session, admin, client_id="abc", client_secret="xyz")
    assert client.get("/api/v1/sources/oura", headers=auth(user)).json()["configured"] is True
