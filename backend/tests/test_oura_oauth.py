from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlmodel import Session

from app.core.config import get_settings
from app.core.crypto import decrypt_secret
from app.models import OAuthState, OuraConnection, Sex, User, UserProfile
from app.services import oura_client, oura_oauth
from app.services.oura_client import OuraAuthError, OuraClient, OuraError
from tests.oura_fake import auth, connect


def _start(client, user) -> dict:
    res = client.get("/api/v1/sources/oura/connect", params={"origin": "http://localhost:3000"}, headers=auth(user))
    assert res.status_code == 200
    return {k: v[0] for k, v in parse_qs(urlparse(res.json()["url"]).query).items()}


def test_connect_cuando_configurado_entonces_url_de_oura_con_state_y_scopes(client, user, session, oura):
    params = _start(client, user)
    assert params["client_id"] == "cliente-de-prueba"
    assert params["redirect_uri"] == "http://localhost:3000/api/v1/sources/oura/callback"
    assert params["scope"] == oura_oauth.SCOPES and params["code_challenge_method"] == "S256"
    pending = session.get(OAuthState, params["state"])
    assert pending.provider == "oura" and pending.user_id == user.id


def test_connect_cuando_sin_origen_permitido_entonces_usa_la_url_publica(client, user, oura):
    res = client.get("/api/v1/sources/oura/connect", params={"origin": "https://malo.example"}, headers=auth(user))
    redirect = parse_qs(urlparse(res.json()["url"]).query)["redirect_uri"][0]
    assert not redirect.startswith("https://malo.example")


def test_connect_cuando_no_configurado_entonces_409(client, user, monkeypatch):
    monkeypatch.setattr(get_settings(), "oura_client_id", "")
    res = client.get("/api/v1/sources/oura/connect", headers=auth(user))
    assert res.status_code == 409


def test_callback_cuando_ok_entonces_guarda_tokens_cifrados_perfil_vacio_y_encola_historico(
    client, user, session, oura, queued
):
    session.add(UserProfile(user_id=user.id, weight_kg=68.0))  # el peso ya puesto no se pisa
    session.commit()
    state = _start(client, user)["state"]
    res = client.get("/api/v1/sources/oura/callback", params={"state": state, "code": "c0d3"}, follow_redirects=False)
    assert res.status_code == 303 and res.headers["location"] == "http://localhost:3000/ajustes?oura=ok"
    form = oura.form()
    assert form["grant_type"] == "authorization_code" and form["code"] == "c0d3"
    assert form["client_secret"] == "secreto-de-prueba" and form["code_verifier"]
    session.expire_all()
    conn = session.get(OuraConnection, user.id)
    assert conn.oura_user_id == "oura-1" and conn.status == "ok"
    assert "at-nuevo" not in conn.access_token_enc and decrypt_secret(conn.access_token_enc) == "at-nuevo"
    assert "heartrate" in conn.scopes.split()
    profile = session.get(UserProfile, user.id)
    assert profile.weight_kg == 68.0 and profile.height_cm == 178.0 and profile.sex == Sex.MALE
    assert profile.birth_date is None  # la edad no se convierte en una fecha inventada
    assert queued == [("oura_import_history_task", [user.id])]
    assert session.get(OAuthState, state) is None  # un solo uso


def test_callback_cuando_state_desconocido_entonces_redirige_con_error(client, oura):
    res = client.get("/api/v1/sources/oura/callback", params={"state": "x", "code": "c"}, follow_redirects=False)
    assert res.status_code == 303 and "oura=error&motivo=autorizacion" in res.headers["location"]


def test_callback_cuando_oura_rechaza_el_codigo_entonces_error_y_sin_conexion(client, user, session, oura, queued):
    oura.tokens.append((400, {"error": "invalid_grant"}))
    state = _start(client, user)["state"]
    res = client.get("/api/v1/sources/oura/callback", params={"state": state, "code": "c"}, follow_redirects=False)
    assert "oura=error" in res.headers["location"]
    assert session.get(OuraConnection, user.id) is None and queued == []


def test_callback_cuando_el_anillo_esta_en_otra_cuenta_entonces_error(client, user, session, oura, queued):
    other = User(email="otra@example.com", password_hash="x")
    session.add(other)
    session.commit()
    connect(session, other)
    state = _start(client, user)["state"]
    res = client.get("/api/v1/sources/oura/callback", params={"state": state, "code": "c"}, follow_redirects=False)
    assert "motivo=anillo_en_otra_cuenta" in res.headers["location"]
    assert session.get(OuraConnection, user.id) is None


def test_cliente_cuando_token_caducado_entonces_lo_renueva_antes_de_pedir(session, user, oura):
    conn = connect(session, user, expires_in=timedelta(seconds=-10))
    oura.collections["daily_sleep"] = [{"id": "a", "day": "2026-10-20", "score": 80}]
    assert OuraClient(session, conn).collection("daily_sleep") == [{"id": "a", "day": "2026-10-20", "score": 80}]
    assert oura.form()["grant_type"] == "refresh_token" and oura.form()["refresh_token"] == "rt-viejo"
    data_request = [r for r in oura.requests if r.url.path.endswith("daily_sleep")][0]
    assert data_request.headers["authorization"] == "Bearer at-nuevo"
    assert decrypt_secret(session.get(OuraConnection, user.id).refresh_token_enc) == "rt-nuevo"


def test_refresh_cuando_oura_lo_rechaza_entonces_conexion_expired(session, user, oura):
    conn = connect(session, user, expires_in=timedelta(seconds=-10))
    oura.tokens.append((401, {"error": "invalid_grant"}))
    with pytest.raises(OuraAuthError):
        OuraClient(session, conn).collection("daily_sleep")
    session.expire_all()
    row = session.get(OuraConnection, user.id)
    assert row.status == "expired" and "caducado" in row.last_error
    with pytest.raises(OuraAuthError):  # caducada: ni lo intenta
        OuraClient(session, row)


def test_cliente_cuando_401_entonces_renueva_y_reintenta_una_vez(session, user, oura):
    conn = connect(session, user)
    oura.fail["/v2/usercollection/tag"] = [401]
    assert OuraClient(session, conn).collection("tag") == []
    assert oura.form()["grant_type"] == "refresh_token"


def test_paginacion_cuando_hay_next_token_entonces_trae_todas_las_paginas(session, user, oura):
    conn = connect(session, user)
    oura.page_size = 2
    oura.collections["tag"] = [{"id": str(i)} for i in range(5)]
    assert [d["id"] for d in OuraClient(session, conn).collection("tag")] == ["0", "1", "2", "3", "4"]
    assert [r.url.params.get("next_token") for r in oura.requests if r] == [None, "2", "4"]


def test_429_cuando_hay_retry_after_entonces_espera_y_reintenta(session, user, oura):
    conn = connect(session, user)
    oura.fail["/v2/usercollection/tag"] = [429, 503]
    oura.collections["tag"] = [{"id": "t"}]
    assert OuraClient(session, conn).collection("tag") == [{"id": "t"}]
    assert oura.waits == [0.0, 0.0]


def test_5xx_cuando_no_se_recupera_entonces_error_legible(session, user, oura):
    conn = connect(session, user)
    oura.fail["/v2/usercollection/tag"] = [500] * (oura_client.MAX_RETRIES + 1)
    with pytest.raises(OuraError, match="no está disponible"):
        OuraClient(session, conn).collection("tag")
    assert len(oura.waits) == oura_client.MAX_RETRIES


def test_apply_personal_info_cuando_perfil_completo_entonces_no_lo_toca(session: Session, user):
    from datetime import date

    session.add(UserProfile(user_id=user.id, weight_kg=60, height_cm=165, sex=Sex.FEMALE, birth_date=date(1990, 1, 1)))
    session.commit()
    oura_oauth.apply_personal_info(session, user.id, {"weight": 90, "height": 1.9, "biological_sex": "male", "age": 20})
    p = session.get(UserProfile, user.id)
    assert (p.weight_kg, p.height_cm, p.sex, p.birth_date) == (60, 165, Sex.FEMALE, date(1990, 1, 1))


def test_estado_cuando_conectado_entonces_contrato(client, user, session, oura):
    conn = connect(session, user)
    conn.ring = {"model": "gen3", "color": "silver", "size": 9, "firmware": "2.9.1", "battery_level": 64,
                 "battery_at": datetime(2026, 10, 20, 8, tzinfo=UTC).isoformat()}  # fmt: skip
    session.add(conn)
    session.commit()
    data = client.get("/api/v1/sources/oura", headers=auth(user)).json()
    assert set(data) == {"configured", "connected", "status", "last_sync_at", "last_error", "scopes", "ring",
                         "recovery_source", "has_watch", "history"}  # fmt: skip
    assert data["configured"] and data["connected"] and data["status"] == "ok" and data["last_error"] is None
    assert data["scopes"] == ["daily", "heartrate"] and data["recovery_source"] == "auto"
    assert data["ring"] == {"model": "gen3", "color": "silver", "size": 9, "firmware": "2.9.1", "battery_level": 64,
                            "battery_at": "2026-10-20T08:00:00Z"}  # fmt: skip
    assert data["history"] == {"status": "done", "from": None, "to": None} and data["has_watch"] is False


def test_estado_cuando_sin_conectar_entonces_valores_vacios(client, user):
    data = client.get("/api/v1/sources/oura", headers=auth(user)).json()
    assert data["connected"] is False and data["status"] is None and data["ring"] is None
    assert data["history"] == {"status": "idle", "from": None, "to": None} and data["scopes"] == []
