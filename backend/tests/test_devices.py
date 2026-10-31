"""Amazfit (Zepp), Xiaomi (Mi Fitness) y la API de relojes por cuenta de marca, con las marcas simuladas."""

import base64
import contextlib
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.core.security import create_token
from app.models import Activity, User
from app.services import devices, modules
from app.services.devices import xiaomi, zepp


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


START = datetime.now(UTC).replace(microsecond=0) - timedelta(days=2)


# ─── Zepp ────────────────────────────────────────────────────────────────────


def test_track_de_zepp_cuando_viene_en_deltas_entonces_se_decodifica_gps_altitud_y_fc():
    detail = {
        "time": "0;10;10",
        "longitude_latitude": "4040000000,-370000000;1000,1000;1000,1000",
        "altitude": "65000;65100;-2000000",
        "heart_rate": "1,120;10,10;10,5",
    }
    pts = zepp.track_points(detail, START)
    assert [p["time"] - START for p in pts] == [timedelta(0), timedelta(seconds=10), timedelta(seconds=20)]
    assert pts[1]["lat"] == pytest.approx(40.40001) and pts[1]["lon"] == pytest.approx(-3.69999)
    assert [p["ele"] for p in pts] == [650.0, 651.0, None]
    assert [p["hr"] for p in pts] == [None, 120.0, 130.0]  # la última FC medida hasta cada punto


def test_entreno_de_zepp_cuando_hay_resumen_entonces_sus_cifras_mandan():
    summary = {"trackid": str(int(START.timestamp())), "type": "1", "run_time": "1800", "dis": "5000",
               "calorie": "350", "avg_heart_rate": "150", "max_heart_rate": "-1"}  # fmt: skip
    act = zepp.to_activity(summary, {"time": "0;600;600", "longitude_latitude": "1,1;1,1;1,1"})
    assert (act.sport, act.duration_s, act.distance_m, act.calories, act.avg_hr) == ("running", 1800, 5000, 350, 150)
    assert act.start_time == START and act.streams["time"] == [0, 600, 1200]


@pytest.fixture
def fake_zepp(monkeypatch):
    state = {"expired": False}
    summary = {"trackid": str(int(START.timestamp())), "type": 9, "run_time": 3600, "dis": 30000,
               "source": "run.mi.com"}  # fmt: skip

    def fake_request(method, url, **kwargs):
        if "/registrations/" in url:
            if kwargs["data"]["password"] == "mala":
                return httpx.Response(401)
            return httpx.Response(303, headers={"Location": f"{zepp.REDIRECT}?access=COD"})
        if url.endswith("/v2/client/login"):
            assert kwargs["data"]["code"] == "COD"
            return httpx.Response(200, json={"token_info": {"login_token": "LT", "user_id": 77}})
        if url.endswith("/app_tokens"):
            return httpx.Response(200, json={"token_info": {"app_token": "AT"}})
        if state["expired"]:
            return httpx.Response(401)
        assert kwargs["headers"]["apptoken"] == "AT" and kwargs["params"]["userid"] == "77"
        if url.endswith("history.json"):
            return httpx.Response(200, json={"data": {"summary": [summary], "next": -1}})
        if url.endswith("detail.json"):
            return httpx.Response(200, json={"data": {"time": "0;1800;1800", "heart_rate": "1,140;1800,5"}})
        return httpx.Response(404)

    monkeypatch.setattr(zepp, "_request", fake_request)
    return state


def test_zepp_cuando_se_conecta_y_sincroniza_entonces_importa_sin_guardar_la_contrasena(session, user, fake_zepp):
    conn = devices.connect(session, user.id, "zepp", "yo@example.com", "clave-9")
    assert devices.read_session(conn) == {"app_token": "AT", "user_id": "77"} and "clave-9" not in conn.session_enc
    assert devices.sync(session, user.id, "zepp") == 1
    act = session.query(Activity).filter(Activity.user_id == user.id).one()
    assert (act.source, act.sport, act.distance_m) == ("zepp", "cycling", 30000)


def test_zepp_cuando_la_contrasena_es_mala_entonces_error_claro(session, user, fake_zepp):
    with pytest.raises(devices.DeviceError, match="no aceptó"):
        devices.connect(session, user.id, "zepp", "yo@example.com", "mala")


def test_zepp_cuando_el_mismo_entreno_ya_vino_de_otra_fuente_entonces_no_se_duplica(session, user, fake_zepp):
    session.add(Activity(user_id=user.id, sport="cycling", start_time=START + timedelta(seconds=30),
                         duration_s=3610, source="garmin", external_id="g1"))  # fmt: skip
    session.commit()
    devices.connect(session, user.id, "zepp", "yo@example.com", "clave-9")
    assert devices.sync(session, user.id, "zepp") == 0
    assert session.query(Activity).filter(Activity.user_id == user.id).count() == 1


# ─── Xiaomi ──────────────────────────────────────────────────────────────────

SSECURITY = base64.b64encode(b"s" * 16).decode()


def test_cifrado_de_xiaomi_cuando_se_cifra_y_descifra_entonces_vuelve_igual():
    nonce = xiaomi.new_nonce()
    body = base64.b64encode(xiaomi._Rc4(base64.b64decode(xiaomi.signed_nonce(SSECURITY, nonce))).apply(
        json.dumps({"code": 0, "x": 1}).encode())).decode()  # fmt: skip
    assert xiaomi.decrypt_body(body, nonce, SSECURITY) == {"code": 0, "x": 1}
    enc = xiaomi.encrypt_params("/app/v1/data/x", {"data": "{}"}, nonce, SSECURITY)
    assert set(enc) == {"data", "rc4_hash__", "signature", "_nonce"} and enc["data"] != "{}"


def test_rc4_de_xiaomi_cuando_se_usa_entonces_descarta_los_primeros_1024_bytes():
    plain = b"hola"
    full = xiaomi._Rc4.__new__(xiaomi._Rc4)
    s, j = list(range(256)), 0
    for i in range(256):
        j = (j + s[i] + b"k"[0]) & 0xFF
        s[i], s[j] = s[j], s[i]
    full.s, full.i, full.j = s, 0, 0
    keystream = full.apply(bytes(1028))[1024:]
    assert xiaomi._Rc4(b"k").apply(plain) == bytes(a ^ b for a, b in zip(plain, keystream, strict=True))


def _encrypted(payload: dict, params: dict) -> str:
    key = base64.b64decode(xiaomi.signed_nonce(SSECURITY, params["_nonce"]))
    return base64.b64encode(xiaomi._Rc4(key).apply(json.dumps(payload).encode())).decode()


@pytest.fixture
def fake_xiaomi(monkeypatch):
    value = {"start_time": int(START.timestamp()), "end_time": int(START.timestamp()) + 1500, "duration": 1500,
             "distance": 4000, "calories": 300, "avg_hrm": 148, "sport_type": 1, "timezone": 4}  # fmt: skip
    state = {"approved": True}

    def fake_request(method, url, **kwargs):
        url = str(url)
        if "longPolling/loginUrl" in url:
            body = {"code": 0, "loginUrl": "https://account.xiaomi.com/l", "qr": "https://account.xiaomi.com/qr.png",
                    "lp": "https://lp"}  # fmt: skip
            return httpx.Response(200, text=xiaomi.SAFE_PREFIX + json.dumps(body))
        if url == "https://account.xiaomi.com/qr.png":
            return httpx.Response(200, content=b"PNG", headers={"content-type": "image/png"})
        if url == "https://lp":
            if not state["approved"]:
                raise devices.DeviceError("El QR ha caducado sin aprobarse. Genera otro.")
            body = {"code": 0, "userId": 9, "cUserId": "c9", "ssecurity": SSECURITY, "nonce": 123,
                    "location": "https://sts.example/x?d=a%2Bb&_ssign=S%3D"}  # fmt: skip
            return httpx.Response(200, text=xiaomi.SAFE_PREFIX + json.dumps(body))
        if str(url).startswith("https://sts.example"):
            # Xiaomi solo da el token si la URL conserva su query original (firma incluida).
            assert str(url).startswith("https://sts.example/x?d=a%2Bb&_ssign=S%3D&clientSign=")
            return httpx.Response(200, headers={"set-cookie": "serviceToken=ST; Path=/"})
        assert url.startswith("https://de.hlth.io.mi.com/") and "serviceToken=ST" in kwargs["headers"]["Cookie"]
        payload = {"code": 0, "result": {"sport_records": [{"time": value["start_time"], "value": json.dumps(value)}],
                                         "has_more": False}}  # fmt: skip
        return httpx.Response(200, text=_encrypted(payload, kwargs["params"]))

    monkeypatch.setattr(xiaomi, "_request", fake_request)
    return state


def test_xiaomi_cuando_se_aprueba_el_qr_entonces_guarda_la_sesion_e_importa(session, user, fake_xiaomi, monkeypatch):
    from app.tasks import devices as tasks

    monkeypatch.setattr(tasks, "Session", lambda _engine: contextlib.nullcontext(session))
    pending = xiaomi.start_qr()
    devices.save_session(session, user.id, "xiaomi", {**pending, "region": "de"}, "", status="pending")
    assert tasks.xiaomi_wait_qr_task(user.id) == "ok"
    conn = devices.get_connection(session, user.id, "xiaomi")
    assert conn.status == "ok" and devices.read_session(conn)["service_token"] == "ST"
    act = session.query(Activity).filter(Activity.user_id == user.id).one()
    assert (act.source, act.sport, act.distance_m, act.timezone) == ("xiaomi", "running", 4000, "+01:00")


def test_xiaomi_cuando_el_qr_caduca_entonces_la_conexion_queda_con_error(session, user, fake_xiaomi, monkeypatch):
    from app.tasks import devices as tasks

    monkeypatch.setattr(tasks, "Session", lambda _engine: contextlib.nullcontext(session))
    fake_xiaomi["approved"] = False
    devices.save_session(session, user.id, "xiaomi", {**xiaomi.start_qr(), "region": "de"}, "", status="pending")
    assert tasks.xiaomi_wait_qr_task(user.id) == "error"
    conn = devices.get_connection(session, user.id, "xiaomi")
    assert conn.status == "error" and "caducado" in conn.last_error


def test_xiaomi_cuando_la_conexion_esta_pendiente_entonces_no_se_sincroniza(session, user):
    devices.save_session(session, user.id, "xiaomi", {"lp": "x"}, "", status="pending")
    assert devices.sync(session, user.id, "xiaomi") == 0


# ─── API ─────────────────────────────────────────────────────────────────────


def test_api_cuando_se_conecta_suunto_entonces_lo_lista_y_encola_la_sincronizacion(client, user, monkeypatch):
    from app.tasks import devices as tasks

    queued: list = []
    monkeypatch.setattr(tasks.device_sync_task, "apply_async", lambda **kw: queued.append(kw))
    monkeypatch.setattr(devices, "providers", lambda: {
        "suunto": devices.Provider("suunto", "Suunto", lambda a, p: ({"session_key": "SK"}, "corredor"),
                                   lambda s, d: []),
        "zepp": zepp.PROVIDER, "xiaomi": xiaomi.PROVIDER,
    })  # fmt: skip
    assert client.get("/api/v1/sources/devices", headers=auth(user)).json()["connections"] == []
    res = client.post("/api/v1/sources/devices/suunto", json={"account": "yo@example.com", "password": "clave-9"},
                      headers=auth(user))  # fmt: skip
    data = res.json()
    assert res.status_code == 200 and "clave-9" not in str(data)
    assert data["connections"][0] | {"last_sync_at": None} == {
        "provider": "suunto", "label": "Suunto", "account": "corredor", "status": "ok",
        "last_sync_at": None, "last_error": "",
    }  # fmt: skip
    assert queued and queued[0]["args"][1] == "suunto"
    assert client.post("/api/v1/sources/devices/suunto/sync", headers=auth(user)).status_code == 202
    assert client.delete("/api/v1/sources/devices/suunto", headers=auth(user)).status_code == 204
    assert client.get("/api/v1/sources/devices", headers=auth(user)).json()["connections"] == []


def test_api_cuando_xiaomi_no_admite_contrasena_entonces_422(client, user):
    res = client.post("/api/v1/sources/devices/xiaomi", json={"account": "yo@example.com", "password": "x"},
                      headers=auth(user))  # fmt: skip
    assert res.status_code == 422


def test_api_cuando_se_pide_el_qr_de_xiaomi_entonces_queda_pendiente(client, user, fake_xiaomi, monkeypatch):
    from app.tasks import devices as tasks

    queued: list = []
    monkeypatch.setattr(tasks.xiaomi_wait_qr_task, "apply_async", lambda **kw: queued.append(kw))
    res = client.post("/api/v1/sources/devices/xiaomi/qr", json={"region": "de"}, headers=auth(user))
    assert res.json() == {"login_url": "https://account.xiaomi.com/l", "qr": "data:image/png;base64,UE5H"} and queued
    conns = client.get("/api/v1/sources/devices", headers=auth(user)).json()["connections"]
    assert [(c["provider"], c["status"]) for c in conns] == [("xiaomi", "pending")]
    assert "lp" not in str(conns)


def test_api_cuando_el_modulo_esta_apagado_entonces_404(client, session, user):
    modules.set_modules(session, {"suunto": False}, None)
    res = client.post("/api/v1/sources/devices/suunto", json={"account": "yo@example.com", "password": "x"},
                      headers=auth(user))  # fmt: skip
    assert res.status_code == 404 and res.json()["error"]["code"] == "MODULE_DISABLED"
    assert "suunto" not in client.get("/api/v1/sources/devices", headers=auth(user)).json()["enabled"]


def test_qr_de_xiaomi_cuando_viene_de_otro_dominio_entonces_no_se_descarga():
    with pytest.raises(devices.DeviceError, match="no seguro"):
        xiaomi._qr_image("https://evil.example/qr.png", "D")
