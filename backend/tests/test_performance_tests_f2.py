"""Tests de rendimiento, fase 2: FTP con potencia, CSS de natación, lactato escalonado y laboratorio."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlmodel import Session

from app.core.security import create_token
from app.models import Activity, Lap, User
from app.services import ai_tools, lactate
from app.services import performance_tests as pt
from app.services.file_import import ImportedActivity, save_imported
from app.services.zones import estimate_thresholds

DAY = date.today() - timedelta(days=2)
START = datetime.combine(DAY, datetime.min.time(), tzinfo=UTC) + timedelta(hours=8)


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def _ride(session: Session, user: User, segments: list[tuple[int, float, float]]) -> Activity:
    """Bici sintética a 1 punto/s: cada tramo = (segundos, vatios, FC)."""
    time, dist, hr, power = [], [], [], []
    t, d = 0, 0.0
    for seconds, watts, bpm in segments:
        for _ in range(seconds):
            time.append(float(t))
            dist.append(round(d, 1))
            hr.append(bpm)
            power.append(watts)
            t += 1
            d += 8.0
    streams = {"time": time, "distance": dist, "hr": hr, "power": power}
    act = ImportedActivity(sport="cycling", start_time=START, duration_s=float(t), distance_m=d, max_hr=185,
                           streams=streams)  # fmt: skip
    activity, _ = save_imported(session, user.id, act, "fit")
    return activity


def test_ftp_20_min(session: Session, user: User):
    act = _ride(session, user, [(900, 150, 120), (300, 300, 165), (600, 120, 125), (1200, 280, 166),
                                (600, 120, 120)])  # fmt: skip
    row = pt.test_from_activity(session, act, "bike_ftp_20min")
    assert row.status == "detected"
    assert row.results["best_power_w"] == 280 and row.results["ftp"] == 266  # 95 %
    assert row.results["power_zones"][3] == {"name": "Z4 Umbral", "min": 239, "max": 278}
    assert row.results["lthr"] == round(166 * 0.95)


def test_rampa(session: Session, user: User):
    steps = [(60, 150 + 20 * k, 120 + 4 * k) for k in range(11)]  # 150 → 350 W
    act = _ride(session, user, [(600, 120, 115), *steps, (300, 100, 120)])
    row = pt.test_from_activity(session, act, "bike_ramp")
    assert row.results["ftp"] == round(350 * 0.75)


def test_ftp_sin_potencia_falla(session: Session, user: User):
    act = _ride(session, user, [(2400, 0, 150)])
    act_streams = pt.Series.load(session, act.id)
    assert not act_streams.has_power
    row = pt.test_from_activity(session, act, "bike_ftp_20min")
    assert row.status == "failed" and "potencia" in row.checks[0]["message"]


def test_css_por_vueltas(session: Session, user: User):
    act = Activity(user_id=user.id, sport="lap_swimming", start_time=START, duration_s=2400, distance_m=1600,
                   source="fit")  # fmt: skip
    session.add(act)
    session.flush()
    # Calentamiento 400, test de 400 (por largos de 50 m), descanso, 200 de una vuelta.
    laps = [(400, 480)] + [(50, 45)] * 8 + [(0, 300), (200, 170), (200, 240)]
    offset = 0.0
    for i, (meters, seconds) in enumerate(laps):
        session.add(Lap(activity_id=act.id, index=i, start_offset_s=offset, duration_s=seconds, distance_m=meters))
        offset += seconds
    session.commit()
    row = pt.test_from_activity(session, act, "swim_css")
    assert (row.results["t400_s"], row.results["t200_s"]) == (360, 170)
    assert row.results["css_pace_s_100m"] == 95  # 200 m / 190 s = 1,053 m/s
    assert row.results["css_zones"][3]["name"] == "Z4 Umbral (CSS)"


def test_css_manual_api(client, user):
    h = auth(user)
    res = client.post(
        "/api/v1/tests",
        json={"protocol": "swim_css", "sport": "swimming", "test_date": DAY.isoformat(), "t400_s": 400, "t200_s": 190},
        headers=h,
    )
    assert res.status_code == 201, res.text
    assert res.json()["results"]["css_pace_s_100m"] == 105  # 200 m / 210 s
    assert "CSS 1:45/100 m" in res.json()["summary"]
    bad = client.post(
        "/api/v1/tests",
        json={"protocol": "swim_css", "sport": "swimming", "test_date": DAY.isoformat(), "t400_s": 180, "t200_s": 190},
        headers=h,
    )
    assert bad.status_code == 422


STEPS = [  # ritmo s/km, lactato, FC
    (360, 1.0, 130), (330, 1.1, 140), (300, 1.4, 150), (280, 2.0, 158), (260, 3.2, 167), (240, 5.5, 178),
]  # fmt: skip


def test_lactato_umbrales():
    steps = [lactate.Step(1000 / p, la, hr) for p, la, hr in STEPS]
    r, checks = lactate.analyze(steps)
    assert r["baseline_mmol"] == 1.0
    assert 1000 / 300 < r["lt1"] < 1000 / 280  # cruza 1,5 mmol/L entre 5:00 y 4:40
    assert r["obla"] == pytest.approx(1000 / 260 + (4.0 - 3.2) / (5.5 - 3.2) * (1000 / 240 - 1000 / 260), abs=0.001)
    assert r["lt2_method"] == "dmax" and r["lt1"] < r["lt2"] <= r["obla"] + 0.2
    assert 150 < r["lt1_hr"] < r["lt2_hr"] < 178
    assert all(c["ok"] for c in checks)


def test_lactato_sin_subida_no_da_lt2():
    flat = [lactate.Step(3 + k * 0.2, 1.0 + 0.05 * k, 140) for k in range(5)]
    r, checks = lactate.analyze(flat)
    assert "lt2" not in r and not next(c for c in checks if c["key"] == "lt2")["ok"]
    with pytest.raises(lactate.LactateError):
        lactate.analyze(flat[:3])


def test_api_lactato_carrera_manda_en_zonas(client, user, session):
    h = auth(user)
    body = {"sport": "running", "test_date": DAY.isoformat(), "notes": "Lactate Pro",
            "steps": [{"pace_s_km": p, "lactate": la, "hr": hr} for p, la, hr in STEPS]}  # fmt: skip
    res = client.post("/api/v1/tests/lactate", json=body, headers=h)
    assert res.status_code == 201, res.text
    test = res.json()
    assert test["status"] == "confirmed" and test["protocol"] == "lactate"
    r = test["results"]
    assert 240 <= r["threshold_pace_s_km"] <= 270 and r["lt1_pace_s_km"] > r["threshold_pace_s_km"]
    assert len(r["lactate_steps"]) == 6
    thr = estimate_thresholds(session, user.id)
    assert thr["pace_source"] == "test" and thr["threshold_pace_s_km"] == r["threshold_pace_s_km"]
    assert thr["lthr"] == r["lthr"]
    flat = {**body, "steps": [{"pace_s_km": 360 - 10 * k, "lactate": 1.0} for k in range(5)]}
    assert client.post("/api/v1/tests/lactate", json=flat, headers=h).status_code == 422
    short = {**body, "steps": body["steps"][:3]}
    assert client.post("/api/v1/tests/lactate", json=short, headers=h).status_code == 422


def test_api_lactato_bici_desde_vueltas(client, user, session):
    act = _ride(session, user, [(600, 100, 110)])
    for i, (watts, hr) in enumerate([(150, 120), (190, 130), (230, 142), (270, 155), (310, 168), (350, 178)]):
        session.add(Lap(activity_id=act.id, index=i, start_offset_s=i * 240, duration_s=240, avg_hr=hr,
                        metrics={"avg_power": watts}))  # fmt: skip
    session.commit()
    lac = [1.1, 1.2, 1.6, 2.6, 4.6, 8.0]
    body = {"sport": "cycling", "test_date": DAY.isoformat(), "activity_id": act.id,
            "steps": [{"lap_index": i, "lactate": la} for i, la in enumerate(lac)]}  # fmt: skip
    res = client.post("/api/v1/tests/lactate", json=body, headers=auth(user))
    assert res.status_code == 201, res.text
    r = res.json()["results"]
    assert 270 < r["ftp"] < 310 and r["lt1_power"] < r["ftp"]
    assert r["power_zones"] and r["hr_zones"]
    assert res.json()["activity_id"] == act.id


def test_api_informe_de_laboratorio(client, user, session):
    h = auth(user)
    run = client.post("/api/v1/tests", json={
        "protocol": "lab", "sport": "running", "test_date": DAY.isoformat(), "vo2max": 58.2, "hr_max": 194,
        "vt1_hr": 150, "vt1_pace_s_km": 300, "vt2_hr": 174, "vt2_pace_s_km": 248,
    }, headers=h)  # fmt: skip
    assert run.status_code == 201, run.text
    r = run.json()["results"]
    assert (r["lthr"], r["threshold_pace_s_km"], r["lt1_hr"], r["vo2max"]) == (174, 248, 150, 58.2)
    thr = estimate_thresholds(session, user.id)
    assert (thr["lthr"], thr["threshold_pace_s_km"]) == (174, 248)
    bike = client.post("/api/v1/tests", json={
        "protocol": "lab", "sport": "cycling", "test_date": DAY.isoformat(), "vt2_hr": 168, "vt2_power": 285,
        "vt1_power": 210, "vt2_pace_s_km": 250,
    }, headers=h)  # fmt: skip
    rb = bike.json()["results"]
    assert rb["ftp"] == 285 and "threshold_pace_s_km" not in rb and rb["power_zones"][0]["max"] == 156
    # La bici no cambia las zonas de carrera.
    assert estimate_thresholds(session, user.id)["lthr"] == 174


def test_preferencia_lactato(client, user):
    h = auth(user)
    assert client.get("/api/v1/tests/preferences", headers=h).json() == {"lactate_tests": True}
    assert client.put("/api/v1/tests/preferences", json={"lactate_tests": False}, headers=h).status_code == 200
    assert client.get("/api/v1/tests/preferences", headers=h).json() == {"lactate_tests": False}


def test_la_ia_ve_los_tests(client, user, session):
    pt.manual_test(session, user.id, "cycling", DAY, {"ftp": 250})
    _, out = ai_tools.zonas_y_umbrales(session, user.id, {})
    assert out["tests"][0]["resultado"] == "FTP 250 W" and out["tests"][0]["estado"] == "aplicado"
