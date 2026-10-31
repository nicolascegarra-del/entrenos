"""Suunto: firma del login, TOTP, sesión caducada y sincronización sin duplicados (Suunto simulado)."""

import hashlib
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.models import Activity
from app.services import devices
from app.services.devices import suunto
from app.services.file_import import ImportedActivity

# Vectores de referencia de tajchert/suuntool (internal/auth/*_test.go).
LOGIN_SECRET_HEX = (
    "77764342455243417a3730794252723964531c7e2b5803454d394c5564065765451d774e5c4b666f2059584252402d002e01ef"
    "bfbdefbfbdefbfbd5f12633667570c5e7a2e505515245a2d4d204a230c577f6e253437050c57791376"
)


def test_clave_de_login_cuando_se_deriva_entonces_coincide_con_la_de_referencia():
    assert suunto._secret(suunto._LOGIN_KEY, suunto.PACKAGE).hex() == LOGIN_SECRET_HEX


def test_firma_cuando_se_firman_parametros_entonces_coincide_con_la_de_referencia():
    got = suunto.sign("login", [("l", "foo@bar.com"), ("p", "Pass123")])
    assert got == "Sf8mC1rPA6rrZh0uHpdwh-TkSlQLO0hkKs4S_6vdBqo"


def test_totp_cuando_se_calcula_para_un_email_entonces_coincide_con_la_de_referencia():
    master = suunto._secret(suunto._TOTP_KEY, suunto._TOTP_XOR).decode()
    key = hashlib.pbkdf2_hmac("sha1", bytes(ord(c) & 0xFF for c in master), b"alice@example.com", 100, 32)
    assert key.hex() == "15d70cdb1125776ce85e91af922c2ba6db8917d994bf2a283fc5b249acf72e8e"
    assert suunto.totp("alice@example.com", now_ms=1_000_000 * 30000) == "215251"


@pytest.fixture
def fake_suunto(monkeypatch):
    """Suunto simulado: login, lista de entrenos y FIT (lo parsea un `parse_fit` falso)."""
    start = datetime.now(UTC) - timedelta(days=1)
    state = {"expired": False, "workouts": [{"key": "wk1", "startTime": int(start.timestamp() * 1000)}]}

    def fake_request(method, url, **kwargs):
        if url.endswith("login2"):
            body = kwargs["content"]
            if "p=mala" in body:
                return httpx.Response(401)
            return httpx.Response(200, json={"sessionkey": "SK", "username": "corredor"})
        if state["expired"]:
            return httpx.Response(401)
        assert kwargs["headers"]["STTAuthorization"] == "SK"
        if "/workouts?" in url:
            return httpx.Response(200, json={"error": None, "payload": state["workouts"]})
        if "/exportFit/" in url:
            return httpx.Response(200, content=b"FIT")
        return httpx.Response(404)

    monkeypatch.setattr(suunto, "_request", fake_request)
    monkeypatch.setattr(
        suunto, "parse_fit",
        lambda data: ImportedActivity(sport="running", start_time=start, duration_s=3600, distance_m=10000),
    )  # fmt: skip
    return state


def test_conectar_cuando_las_credenciales_valen_entonces_guarda_solo_la_sesion(session, user, fake_suunto):
    conn = devices.connect(session, user.id, "suunto", "a@b.com", "buena")
    assert conn.status == "ok" and conn.account == "corredor"
    assert "buena" not in conn.session_enc
    assert devices.read_session(conn) == {"session_key": "SK"}


def test_conectar_cuando_la_contrasena_es_mala_entonces_da_error_claro(session, user, fake_suunto):
    with pytest.raises(devices.DeviceError, match="no aceptó"):
        devices.connect(session, user.id, "suunto", "a@b.com", "mala")


def test_sincronizar_cuando_hay_un_entreno_nuevo_entonces_lo_importa_una_sola_vez(session, user, fake_suunto):
    devices.connect(session, user.id, "suunto", "a@b.com", "buena")
    assert devices.sync(session, user.id, "suunto") == 1
    assert devices.sync(session, user.id, "suunto") == 0
    acts = session.query(Activity).filter(Activity.user_id == user.id).all()
    assert [(a.source, a.external_id) for a in acts] == [("suunto", "wk1")]


def test_sincronizar_cuando_la_sesion_caduca_entonces_marca_la_conexion_caducada(session, user, fake_suunto):
    devices.connect(session, user.id, "suunto", "a@b.com", "buena")
    fake_suunto["expired"] = True
    assert devices.sync(session, user.id, "suunto") == 0
    conn = devices.get_connection(session, user.id, "suunto")
    assert conn.status == "expired" and "caducado" in conn.last_error
