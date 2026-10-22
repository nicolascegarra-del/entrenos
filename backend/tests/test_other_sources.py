import base64
import struct
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, select

from app.core.security import create_token
from app.models import Activity, ActivityStream, CorosCredential, DailyMetric, User
from app.services import coros, file_import, health_connect

FIT_EPOCH = datetime(1989, 12, 31, tzinfo=UTC)
START = datetime(2026, 10, 1, 7, 0, tzinfo=UTC)


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


# ─── FIT mínimo (para no depender de ficheros reales) ────────────────────────


def _crc(data: bytes) -> int:
    table = [0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
             0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400]  # fmt: skip
    crc = 0
    for byte in data:
        for nibble in (byte & 0xF, byte >> 4):
            tmp = table[crc & 0xF]
            crc = (crc >> 4) & 0x0FFF
            crc = crc ^ tmp ^ table[nibble]
    return crc


def _fit(points: int = 120, speed: float = 3.0, sport: int = 1) -> bytes:
    """FIT con una sesión y `points` registros de 1 s (carrera en línea recta hacia el norte)."""
    ts = lambda dt: int((dt - FIT_EPOCH).total_seconds())  # noqa: E731
    body = b""
    # Definición local 0 = record (20): timestamp, lat, long, distance, heart_rate, altitude.
    fields = [(253, 4, 0x86), (0, 4, 0x85), (1, 4, 0x85), (5, 4, 0x86), (3, 1, 0x02), (2, 2, 0x84)]
    body += struct.pack("<BBBHB", 0x40, 0, 0, 20, len(fields)) + b"".join(struct.pack("BBB", *f) for f in fields)
    for i in range(points):
        lat = round((37.6 + i * speed / 111_195) / (180 / 2**31))
        body += struct.pack("<BIiiIBH", 0x00, ts(START + timedelta(seconds=i)), lat, round(-0.98 / (180 / 2**31)),
                            round(i * speed * 100), 140 + i % 10, round((20 + i * 0.1 + 500) * 5))  # fmt: skip
    # Definición local 1 = session (18): start_time, sport, elapsed, timer, distance, avg_hr, max_hr.
    sfields = [(2, 4, 0x86), (5, 1, 0x00), (7, 4, 0x86), (8, 4, 0x86), (9, 4, 0x86), (16, 1, 0x02), (17, 1, 0x02)]
    body += struct.pack("<BBBHB", 0x41, 0, 0, 18, len(sfields)) + b"".join(struct.pack("BBB", *f) for f in sfields)
    body += struct.pack("<BIBIIIBB", 0x01, ts(START), sport, (points - 1) * 1000, (points - 1) * 1000,
                        round((points - 1) * speed * 100), 145, 149)  # fmt: skip
    header = struct.pack("<BBHI4s", 12, 0x10, 2132, len(body), b".FIT")
    data = header + body
    return data + struct.pack("<H", _crc(data))


def _gpx(minutes: int = 20, start: datetime = START) -> str:
    pts = "".join(
        f'<trkpt lat="{37.6 + i * 0.0027}" lon="-0.98"><ele>{10 + i}</ele>'
        f"<time>{(start + timedelta(minutes=i)).isoformat()}</time><extensions><gpxtpx:TrackPointExtension>"
        f"<gpxtpx:hr>{150 + i}</gpxtpx:hr></gpxtpx:TrackPointExtension></extensions></trkpt>"
        for i in range(minutes + 1)
    )  # fmt: skip
    return ('<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1" '
            'xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1"><trk><name>Rodaje</name>'
            f"<type>running</type><trkseg>{pts}</trkseg></trk></gpx>")  # fmt: skip


TCX = """<?xml version="1.0"?><TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
<Activities><Activity Sport="Biking"><Lap><Track>
<Trackpoint><Time>2026-10-02T08:00:00Z</Time><Position><LatitudeDegrees>37.6</LatitudeDegrees><LongitudeDegrees>-0.98</LongitudeDegrees></Position><AltitudeMeters>10</AltitudeMeters><DistanceMeters>0</DistanceMeters><HeartRateBpm><Value>120</Value></HeartRateBpm></Trackpoint>
<Trackpoint><Time>2026-10-02T08:10:00Z</Time><Position><LatitudeDegrees>37.65</LatitudeDegrees><LongitudeDegrees>-0.98</LongitudeDegrees></Position><AltitudeMeters>30</AltitudeMeters><DistanceMeters>5500</DistanceMeters><HeartRateBpm><Value>140</Value></HeartRateBpm></Trackpoint>
</Track></Lap></Activity></Activities></TrainingCenterDatabase>"""


# ─── Lectores ────────────────────────────────────────────────────────────────


def test_fit_resumen_y_series():
    act, kind = file_import.parse_file("salida.fit", _fit())
    assert kind == "fit" and act.sport == "running" and act.start_time == START
    assert act.duration_s == 119 and act.distance_m == pytest.approx(357, abs=1) and act.avg_hr == 145
    assert len(act.streams["hr"]) == 120 and act.streams["lat"][0] == pytest.approx(37.6, abs=1e-6)
    assert act.streams["altitude"][0] == pytest.approx(20, abs=0.3)


def test_fit_danado():
    with pytest.raises(file_import.FileImportError):
        file_import.parse_fit(_fit()[:-10] + b"xxxx")


def test_gpx_con_fc():
    act, kind = file_import.parse_file("rodaje.gpx", _gpx().encode())
    assert kind == "gpx" and act.name == "Rodaje" and act.duration_s == 1200
    assert act.avg_hr == 160 and act.max_hr == 170 and 5500 < act.distance_m < 6500 and act.elevation_gain_m == 20


def test_tcx_ciclismo():
    act, kind = file_import.parse_file("bici.tcx", TCX.encode())
    assert kind == "tcx" and act.sport == "cycling" and act.distance_m == 5500 and act.max_hr == 140


@pytest.mark.parametrize(("name", "data", "msg"), [
    ("x.txt", b"hola", "Formato"),
    ("x.gpx", b'<!DOCTYPE x [<!ENTITY a "b">]><gpx/>', "DOCTYPE"),
    ("x.gpx", b"<gpx></gpx>", "puntos"),
])  # fmt: skip
def test_ficheros_no_validos(name, data, msg):
    with pytest.raises(file_import.FileImportError, match=msg):
        file_import.parse_file(name, data)


# ─── Guardar y deduplicar ────────────────────────────────────────────────────


def test_no_duplica_entre_fuentes(session: Session, user: User):
    garmin = Activity(user_id=user.id, sport="running", start_time=START + timedelta(seconds=40), duration_s=1210,
                      garmin_activity_id=99)  # fmt: skip
    session.add(garmin)
    session.commit()
    act, _ = file_import.parse_file("rodaje.gpx", _gpx().encode())
    found, created = file_import.save_imported(session, user.id, act, "gpx")
    assert not created and found.id == garmin.id
    other, created = file_import.save_imported(session, user.id, file_import.parse_fit(_fit()), "fit")
    assert created and other.source == "fit"  # empieza a la misma hora pero dura muy distinto
    assert session.exec(select(ActivityStream).where(ActivityStream.activity_id == other.id)).all()


def test_api_importar_fichero(client, user):
    body = {"filename": "rodaje.gpx", "content_b64": base64.b64encode(_gpx().encode()).decode()}
    first = client.post("/api/v1/imports/file", json=body, headers=auth(user)).json()
    assert first["created"] and first["source"] == "gpx"
    again = client.post("/api/v1/imports/file", json=body, headers=auth(user)).json()
    assert again == {**first, "created": False}
    detail = client.get(f"/api/v1/activities/{first['activity_id']}", headers=auth(user)).json()
    assert detail["name"] == "Rodaje" and "hr" in detail["channels"]
    bad = client.post("/api/v1/imports/file", json={"filename": "a.fit", "content_b64": "no-es-base64!!"},
                      headers=auth(user))  # fmt: skip
    assert bad.status_code == 422


# ─── COROS ───────────────────────────────────────────────────────────────────


class FakeCoros:
    def __init__(self, items: list[dict], login_ok_on: str = coros.BASES[1]):
        self.items, self.login_ok_on, self.calls = items, login_ok_on, []

    def request(self, method, url, **kw):
        self.calls.append(url)
        if url.endswith("/account/login"):
            ok = url.startswith(self.login_ok_on)
            return {"result": "0000", "data": {"accessToken": "tok-123"}} if ok else {"result": "1001", "message": "No"}
        if url.endswith("/activity/query"):
            page = kw["params"]["pageNumber"]
            return {"result": "0000", "data": {"dataList": self.items if page == 1 else []}}
        if url.endswith("/activity/detail/download"):
            return {"result": "0000", "data": {"fileUrl": f"https://oss.coros.com/{kw['params']['labelId']}.fit"}}
        raise AssertionError(url)


def test_coros_conectar_y_sincronizar(session, user, monkeypatch):
    fake = FakeCoros([{"labelId": "L2", "sportType": 100}, {"labelId": "L1", "sportType": 100}])
    monkeypatch.setattr(coros, "_request", fake.request)
    fits = {"L2": _fit(sport=1), "L1": _fit(points=300, sport=2)}
    monkeypatch.setattr(coros, "_download", lambda url: fits[url.rsplit("/", 1)[1][:-4]])
    cred = coros.connect(session, user.id, "yo@example.com", "secreto")
    assert cred.base_url == coros.BASES[1] and "tok-123" not in cred.token_enc  # cifrado
    # L2 y L1 empiezan a la misma hora en el FIT de prueba, pero L1 dura mucho más: no son duplicados.
    assert coros.sync(session, user.id) == 2


def test_coros_para_en_lo_ya_importado(session, user, monkeypatch):
    fake = FakeCoros([{"labelId": "L1", "sportType": 100}])
    monkeypatch.setattr(coros, "_request", fake.request)
    monkeypatch.setattr(coros, "_download", lambda url: _fit())
    coros.connect(session, user.id, "yo@example.com", "x")
    assert coros.sync(session, user.id) == 1
    assert coros.sync(session, user.id) == 0
    assert sum(u.endswith("/download") for u in fake.calls) == 1  # no vuelve a descargar


def test_coros_token_caducado(session, user, monkeypatch):
    def fake(method, url, **kw):
        if url.endswith("/account/login"):
            return {"result": "0000", "data": {"accessToken": "t"}}
        return {"result": "1019", "message": "Access token is invalid"}

    monkeypatch.setattr(coros, "_request", fake)
    coros.connect(session, user.id, "yo@example.com", "x")
    assert coros.sync(session, user.id) == 0
    cred = session.get(CorosCredential, user.id)
    assert cred.status == "expired" and "caducado" in cred.last_error


def test_coros_credenciales_malas(session, user, monkeypatch):
    monkeypatch.setattr(coros, "_request", FakeCoros([], login_ok_on="https://nadie").request)
    with pytest.raises(coros.CorosError, match="No"):
        coros.connect(session, user.id, "yo@example.com", "mal")


def test_api_coros(client, user, monkeypatch):
    queued = []
    monkeypatch.setattr(coros, "_request", FakeCoros([]).request)
    from app.tasks import sources as tasks

    monkeypatch.setattr(tasks.coros_sync_task, "apply_async", lambda **kw: queued.append(kw))
    assert client.post("/api/v1/sources/coros/sync", headers=auth(user)).status_code == 409
    data = client.post("/api/v1/sources/coros", json={"account": "yo@example.com", "password": "clave-9"},
                       headers=auth(user)).json()  # fmt: skip
    assert data["coros"]["status"] == "ok" and queued and "clave-9" not in str(data)
    assert client.delete("/api/v1/sources/coros", headers=auth(user)).status_code == 204
    assert client.get("/api/v1/sources", headers=auth(user)).json()["coros"] is None


# ─── Health Connect ──────────────────────────────────────────────────────────


def _payload(start: datetime = START) -> dict:
    end = start + timedelta(minutes=30)
    return {
        "timestamp": end.isoformat(), "app_version": "1.0", "timezone": "Europe/Madrid",
        "exercise": [{"type": "running", "start_time": start.isoformat(), "end_time": end.isoformat(),
                      "duration_seconds": 1800, "distance_meters": 5000.0, "steps": 5200}],
        "heart_rate": [{"bpm": 150, "time": (start + timedelta(minutes=5)).isoformat()},
                       {"bpm": 170, "time": (start + timedelta(minutes=20)).isoformat()},
                       {"bpm": 60, "time": (start - timedelta(hours=2)).isoformat()}],
        "sleep": [{"session_end_time": "2026-10-01T06:30:00Z", "duration_seconds": 25200, "stages": []}],
        "steps": [{"count": 4000, "start_time": "2026-10-01T00:00:00Z", "end_time": "2026-10-01T12:00:00Z"},
                  {"count": 3000, "start_time": "2026-10-01T12:00:00Z", "end_time": "2026-10-01T23:59:00Z"}],
    }  # fmt: skip


def test_health_connect_webhook(client, user, session):
    token = client.post("/api/v1/sources/health-connect/token", headers=auth(user)).json()["token"]
    assert token.startswith("hc_")
    assert (
        client.post("/api/v1/ingest/health-connect", json=_payload(), headers={"X-Api-Key": "hc_malo"}).status_code
        == 401
    )
    res = client.post("/api/v1/ingest/health-connect", json=_payload(), headers={"X-Api-Key": token}).json()
    assert res == {"exercise": 1, "duplicates": 0, "sleep": 1, "steps_days": 1}
    act = session.exec(select(Activity).where(Activity.source == "health_connect")).one()
    assert act.avg_hr == 160 and act.max_hr == 170 and act.distance_m == 5000 and act.metrics["steps"] == 5200
    assert act.name == "Actividad de Health Connect"
    day = session.exec(select(DailyMetric).where(DailyMetric.user_id == user.id)).one()
    assert day.metrics == {"sleep_seconds": 25200, "steps_daily": 7000}
    again = client.post("/api/v1/ingest/health-connect", json=_payload(), headers={"X-Api-Key": token}).json()
    assert again["duplicates"] == 1 and again["exercise"] == 0
    assert client.get("/api/v1/sources", headers=auth(user)).json()["health_connect"]["hint"] == token[-4:]
    client.delete("/api/v1/sources/health-connect/token", headers=auth(user))
    assert (
        client.post("/api/v1/ingest/health-connect", json=_payload(), headers={"X-Api-Key": token}).status_code == 401
    )


def test_health_connect_no_es_json(client, user, session):
    token = health_connect.create_token(session, user.id)
    res = client.post("/api/v1/ingest/health-connect", content=b"[1, 2]",
                      headers={"X-Api-Key": token, "Content-Type": "application/json"})  # fmt: skip
    assert res.status_code == 422
