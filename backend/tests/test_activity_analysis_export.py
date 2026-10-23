import io
import zipfile
from datetime import UTC, datetime

import pytest
from sqlmodel import Session

from app.core.security import create_token
from app.models import Activity, ActivityRaw, User
from app.services import activity_analysis, activity_export
from app.services.file_import import ImportedActivity, parse_fit, parse_gpx, parse_tcx, save_imported

START = datetime(2026, 10, 20, 7, 0, tzinfo=UTC)


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def _run(session: Session, user: User, gps: bool = True, minutes: int = 40, vo2: float | None = None) -> Activity:
    """Carrera a 3 m/s (5:33 /km) con la FC subiendo en la 2.ª mitad (deriva) y 2 vueltas."""
    n = minutes * 60
    time = [float(i) for i in range(n)]
    dist = [round(i * 3.0, 1) for i in range(n)]
    hr = [140 + (12 if i > n / 2 else 0) for i in range(n)]
    streams = {"time": time, "distance": dist, "hr": hr, "altitude": [100 + (i % 600) / 60 for i in range(n)],
               "cadence": [170.0] * n, "power": [260.0] * n, "speed": [3.0] * n}  # fmt: skip
    if gps:
        streams["lat"] = [37.6 + i * 3.0 / 111_195 for i in range(n)]
        streams["lon"] = [-0.98] * n
    half = n / 2
    act = ImportedActivity(
        sport="running", start_time=START, duration_s=float(n), moving_duration_s=float(n), distance_m=dist[-1],
        avg_hr=146, max_hr=185, elevation_gain_m=20, calories=500, name="Rodaje / test", streams=streams,
        metrics={"vo2max": vo2} if vo2 else {},
        laps=[{"index": k, "start_offset_s": k * half, "duration_s": half, "distance_m": half * 3,
               "avg_hr": 140 + 12 * k, "max_hr": 150 + 12 * k, "avg_speed": 3.0, "metrics": {}} for k in range(2)],
    )  # fmt: skip
    activity, _ = save_imported(session, user.id, act, "fit")
    return activity


def test_analisis_zonas_parciales_y_deriva(session: Session, user: User):
    a = activity_analysis.analysis(session, _run(session, user))
    zones = a["hr_zones"]["zones"]
    assert len(zones) == 5 and a["hr_zones"]["source"]
    assert sum(z["seconds"] for z in zones) == pytest.approx(2400, abs=2)
    assert sum(z["pct"] for z in zones) == pytest.approx(100, abs=0.5)
    splits = a["splits"]
    assert [s["km"] for s in splits] == list(range(1, 8)) and splits[0]["pace_s_km"] == 333  # 7,2 km
    assert splits[-1]["distance_m"] >= 998 and splits[0]["avg_hr"] == 140  # los 197 m finales no llegan a 200
    drift = a["decoupling"]
    assert drift["pct"] == pytest.approx((1 - 140 / 152) * 100, abs=0.3) and drift["level"] == "alta"
    vo2 = a["vo2max"]
    assert vo2["source"] == "estimado" and 30 < vo2["activity"] < 70


def test_vo2max_del_reloj_manda(session: Session, user: User):
    a = activity_analysis.analysis(session, _run(session, user, vo2=54.0))
    assert (a["vo2max"]["activity"], a["vo2max"]["source"]) == (54.0, "reloj")


def test_exportar_gpx_tcx_y_fit_y_volver_a_leer(session: Session, user: User):
    act = _run(session, user)
    gpx, mime, name = activity_export.export(session, act, "gpx")
    assert mime == "application/gpx+xml" and name == "2026-10-20-rodaje---test.gpx"
    back = parse_gpx(gpx.decode())
    assert back.duration_s == pytest.approx(2399) and back.avg_hr == pytest.approx(146, abs=1)
    assert back.streams["cadence"][0] == 85  # por pierna en GPX

    tcx, _, _ = activity_export.export(session, act, "tcx")
    back = parse_tcx(tcx.decode())
    assert back.distance_m == pytest.approx(act.distance_m, abs=5) and back.sport == "running"
    assert b"<ns3:Watts>260</ns3:Watts>" in tcx and b'<Lap StartTime="2026-10-20T07:20:00Z">' in tcx

    fit, mime, _ = activity_export.export(session, act, "fit")
    assert mime == "application/vnd.ant.fit"
    back = parse_fit(fit)
    assert back.sport == "running" and back.duration_s == pytest.approx(2400)
    assert back.distance_m == pytest.approx(act.distance_m, abs=1) and back.calories == 500
    assert back.streams["cadence"][0] == 170 and back.streams["hr"][-1] == 152
    assert len(back.laps) == 2 and back.laps[1]["avg_hr"] == 152
    assert back.streams["lat"][0] == pytest.approx(37.6, abs=1e-5)


def test_gpx_sin_gps_y_formato_raro(session: Session, user: User):
    act = _run(session, user, gps=False)
    with pytest.raises(activity_export.ExportError, match="GPS"):
        activity_export.export(session, act, "gpx")
    with pytest.raises(activity_export.ExportError):
        activity_export.export(session, act, "kml")
    assert activity_export.export(session, act, "tcx")[0].startswith(b"<?xml")


def test_fit_original_de_garmin(session: Session, user: User, monkeypatch):
    act = _run(session, user)
    original = b"\x0e\x20\x00\x00\x00\x00\x00\x00.FIT" + b"original"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("123_ACTIVITY.fit", original)
    session.add(ActivityRaw(activity_id=act.id, summary={}, fit_object_key="fit/1/123.zip"))
    session.commit()

    class Store:
        def get(self, key):
            return buf.getvalue() if key == "fit/1/123.zip" else None

    monkeypatch.setattr("app.services.storage.get_storage", lambda: Store())
    assert activity_export.export(session, act, "fit")[0] == original


def test_api_analisis_y_exportar(client, user, session):
    act = _run(session, user)
    h = auth(user)
    a = client.get(f"/api/v1/activities/{act.id}/analysis", headers=h).json()
    assert len(a["hr_zones"]["zones"]) == 5 and a["splits"]
    res = client.get(f"/api/v1/activities/{act.id}/export?format=tcx", headers=h)
    assert res.status_code == 200 and res.headers["content-disposition"].endswith('.tcx"')
    assert client.get(f"/api/v1/activities/{act.id}/export?format=kml", headers=h).status_code == 422
    other = User(email="otra@example.com", password_hash="x")
    session.add(other)
    session.commit()
    assert client.get(f"/api/v1/activities/{act.id}/export?format=gpx", headers=auth(other)).status_code == 404
