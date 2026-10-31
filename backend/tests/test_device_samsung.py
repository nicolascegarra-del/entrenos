"""Samsung Health: cifrado del login, canje del enlace «ms-app://», entrenos y API (Samsung simulado)."""

import base64
import json
import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cryptography.hazmat.primitives import padding, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.core.security import create_token
from app.models import Activity, User
from app.services import devices
from app.services.devices import samsung

START = datetime.now(UTC).replace(microsecond=0) - timedelta(days=3)
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC_B64 = base64.b64encode(
    KEY.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
).decode()


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def ecb(value: str, key: str) -> str:
    """Cifra como Samsung los campos de la redirección (AES-ECB, PKCS7, hex)."""
    padder = padding.PKCS7(128).padder()
    data = padder.update(value.encode()) + padder.finalize()
    enc = Cipher(algorithms.AES(key.encode()[:16].ljust(16, b"\0")), modes.ECB()).encryptor()
    return (enc.update(data) + enc.finalize()).hex()


def redirect(state: str, response_key: str = "RESPKEY123") -> str:
    q = {
        "state": ecb(response_key, state),
        "auth_server_url": ecb("https://eu-auth2.samsungosp.com", response_key),
        "code": ecb("CODE", response_key),
        "retValue": ecb("yo@example.com", response_key),
    }
    return f"{samsung.REDIRECT_URI}?" + "&".join(f"{k}={v}" for k, v in q.items())


def test_parametros_del_login_cuando_se_cifran_entonces_samsung_los_puede_descifrar():
    payload = {"clientId": "x", "state": "abc"}
    raw = samsung.encrypt_svc_param(payload, 3, PUBLIC_B64)
    env = json.loads(base64.b64decode(__import__("urllib.parse").parse.unquote(raw)))
    key = base64.b64decode(KEY.decrypt(base64.b64decode(env["svcEncKY"]), asym_padding.PKCS1v15()))
    dec = Cipher(algorithms.AES(key), modes.CBC(bytes.fromhex(env["svcEncIV"]))).decryptor()
    padded = dec.update(base64.b64decode(env["svcEncParam"])) + dec.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    assert json.loads(unpadder.update(padded) + unpadder.finalize()) == payload and env["chkDoNum"] == "3"


def test_campo_de_la_redireccion_cuando_se_descifra_entonces_vuelve_igual():
    assert samsung.decrypt_value(ecb("hola mundo", "clave"), "clave") == "hola mundo"


@pytest.fixture
def fake_samsung(monkeypatch):
    state = {"encrypted": False, "registered": 0}
    doc = {"datauuid": "u1", "start_time": int(START.timestamp() * 1000), "duration": 1_800_000, "distance": 5000.0,
           "calorie": 320.0, "mean_heart_rate": 151.0, "max_heart_rate": 178.0, "exercise_type": 1002,
           "time_offset": 3_600_000}  # fmt: skip

    def fake_request(method, url, **kwargs):
        if url == samsung.ENTRY_POINT:
            sign_in = "https://account.samsung.com/accounts/v1/X/signIn"
            return httpx.Response(200, json={"chkDoNum": 3, "pkiPublicKey": PUBLIC_B64, "signInURI": sign_in})
        if url.endswith("/auth/oauth2/authenticate"):
            assert kwargs["data"]["code"] == "CODE" and kwargs["data"]["username"] == "yo@example.com"
            return httpx.Response(200, json={"userauth_token": "MASTER", "userId": "u-9"})
        if url.endswith("/auth/oauth2/v2/authorize"):
            assert kwargs["params"]["userauth_token"] == "MASTER"
            return httpx.Response(200, json={"code": "HC"})
        if url.endswith("/auth/oauth2/token"):
            return httpx.Response(200, json={"access_token": "HEALTH"})
        if url.endswith("/identity/v1/register"):
            state["registered"] += 1
            return httpx.Response(200, json={"registrationId": "R1"})
        if url.endswith("/identity/v1/tokens"):
            assert kwargs["headers"]["x-sc-access-token"] == "HEALTH"
            return httpx.Response(200, json={"tokenType": "Bearer", "accessToken": "CLOUD", "expiresAt": 1})
        if "/documents" in url:
            assert kwargs["headers"]["authorization"] == "Bearer CLOUD"
            env = {"needToDecrypt": True} if state["encrypted"] else {"data": doc}
            return httpx.Response(200, json={"documents": [env]})
        return httpx.Response(404)

    monkeypatch.setattr(samsung, "_request", fake_request)
    return state


def test_login_cuando_se_pega_el_enlace_entonces_guarda_el_token_maestro(fake_samsung):
    url, pending = samsung.start_login()
    assert url.startswith("https://account.samsung.com/accounts/v1/X/signIn?locale=es-ES&svcParam=")
    sess, account = samsung.finish_login(pending, redirect(pending["state"]))
    assert account == "yo@example.com" and sess["master_token"] == "MASTER" and sess["user_id"] == "u-9"


def test_login_cuando_el_enlace_no_es_de_samsung_entonces_error_claro(fake_samsung):
    _, pending = samsung.start_login()
    with pytest.raises(devices.DeviceError, match="ms-app"):
        samsung.finish_login(pending, "https://otra.web/?code=1")


def test_login_cuando_han_pasado_15_minutos_entonces_hay_que_empezar_de_nuevo(fake_samsung):
    _, pending = samsung.start_login()
    pending["created_at"] = int(time.time()) - 16 * 60
    with pytest.raises(devices.DeviceError, match="15 minutos"):
        samsung.finish_login(pending, redirect(pending["state"]))


def test_sincronizar_cuando_hay_entreno_entonces_lo_importa_y_se_registra_una_vez(session, user, fake_samsung):
    _, pending = samsung.start_login()
    sess, account = samsung.finish_login(pending, redirect(pending["state"]))
    devices.save_session(session, user.id, "samsung", sess, account)
    assert devices.sync(session, user.id, "samsung") == 1
    devices.sync(session, user.id, "samsung")
    assert fake_samsung["registered"] == 1  # el registro se guarda en la sesión
    act = session.query(Activity).filter(Activity.user_id == user.id).one()
    assert (act.source, act.sport, act.duration_s, act.distance_m, act.avg_hr, act.timezone) == (
        "samsung", "running", 1800, 5000, 151, "+01:00",
    )  # fmt: skip


def test_sincronizar_cuando_todo_esta_cifrado_entonces_lo_explica(session, user, fake_samsung):
    fake_samsung["encrypted"] = True
    _, pending = samsung.start_login()
    sess, account = samsung.finish_login(pending, redirect(pending["state"]))
    devices.save_session(session, user.id, "samsung", sess, account)
    assert devices.sync(session, user.id, "samsung") == 0
    conn = devices.get_connection(session, user.id, "samsung")
    assert conn.status == "error" and "cifrados" in conn.last_error


def test_api_cuando_se_empieza_y_se_pega_el_enlace_entonces_queda_conectado(client, user, fake_samsung, monkeypatch):
    from app.tasks import devices as tasks

    queued: list = []
    monkeypatch.setattr(tasks.device_sync_task, "apply_async", lambda **kw: queued.append(kw))
    assert client.post("/api/v1/sources/devices/samsung/finish", json={"redirect": "ms-app://" + "x" * 30},
                       headers=auth(user)).status_code == 409  # fmt: skip
    res = client.post("/api/v1/sources/devices/samsung/start", headers=auth(user))
    assert res.status_code == 200 and res.json()["login_url"].startswith("https://account.samsung.com/")
    from sqlmodel import Session

    from app.core.db import engine

    with Session(engine) as s:
        pending = devices.read_session(devices.get_connection(s, user.id, "samsung"))
    res = client.post("/api/v1/sources/devices/samsung/finish", json={"redirect": redirect(pending["state"])},
                      headers=auth(user))  # fmt: skip
    conns = res.json()["connections"]
    assert res.status_code == 200 and [(c["provider"], c["status"]) for c in conns] == [("samsung", "ok")]
    assert queued and queued[0]["args"][1] == "samsung"
