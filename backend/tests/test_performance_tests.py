from datetime import UTC, date, datetime, timedelta

import pytest
from sqlmodel import Session, select

from app.core.security import create_token
from app.models import Activity, PerformanceTest, PlannedSession, User
from app.services import performance_tests as pt
from app.services import progress as prog
from app.services.file_import import ImportedActivity, save_imported
from app.services.zones import estimate_thresholds

DAY = date.today() - timedelta(days=3)
START = datetime.combine(DAY, datetime.min.time(), tzinfo=UTC) + timedelta(hours=8)


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def _activity(session: Session, user: User, segments: list[tuple[int, float, float]], sport: str = "running",
              start: datetime = START, spike: bool = False) -> Activity:  # fmt: skip
    """Actividad sintética a 1 punto/s: cada tramo = (segundos, velocidad m/s, FC)."""
    time, dist, hr = [], [], []
    t, d = 0, 0.0
    for seconds, speed, bpm in segments:
        for _ in range(seconds):
            time.append(float(t))
            dist.append(round(d, 1))
            hr.append(bpm)
            t += 1
            d += speed
    if spike:
        hr[100] = 225  # pico falso del sensor (un solo punto)
    streams = {"time": time, "distance": dist, "hr": hr}
    act = ImportedActivity(sport=sport, start_time=start, duration_s=float(t), distance_m=d,
                           max_hr=max(h for h in hr if h), streams=streams)  # fmt: skip
    activity, _ = save_imported(session, user.id, act, "fit")
    return activity


THIRTY = [(900, 3.0, 130), (600, 4.0, 160), (1200, 4.0, 170), (600, 2.8, 125)]


def test_30_min_detecta_ritmo_y_fc_umbral(session: Session, user: User):
    act = _activity(session, user, THIRTY)
    row = pt.test_from_activity(session, act, "run_30min")
    assert row.status == "detected" and row.source == "activity" and row.test_date == DAY
    assert row.results["threshold_pace_s_km"] == 250  # 4,0 m/s
    assert row.results["lthr"] == 170  # FC media de los últimos 20 min
    assert row.results["window_s"][1] - row.results["window_s"][0] == pytest.approx(1800, abs=2)
    keys = {c["key"]: c["ok"] for c in row.checks}
    assert keys["duracion"] and keys["datos"] and keys["regularidad"] and keys["pulso"]
    assert row.confidence in ("alta", "media")


def test_confirmar_manda_sobre_estimaciones(session: Session, user: User):
    act = _activity(session, user, THIRTY)
    before = estimate_thresholds(session, user.id)
    assert before["lthr_source"] != "test"
    row = pt.confirm(session, pt.test_from_activity(session, act, "run_30min"))
    assert row.status == "confirmed" and row.confirmed_at is not None
    after = estimate_thresholds(session, user.id)
    assert (after["pace_source"], after["threshold_pace_s_km"]) == ("test", 250)
    assert (after["lthr_source"], after["lthr"]) == ("test", 170)
    assert after["test_date"] == DAY.isoformat()
    assert prog.user_thresholds(session, user.id).lthr == 170


def test_test_caducado_ya_no_manda(session: Session, user: User):
    old = START - timedelta(days=70)
    act = _activity(session, user, THIRTY, start=old)
    pt.confirm(session, pt.test_from_activity(session, act, "run_30min"))
    assert estimate_thresholds(session, user.id)["pace_source"] != "test"


def test_actividad_corta_falla_y_no_se_puede_confirmar(session: Session, user: User):
    act = _activity(session, user, [(600, 3.0, 130), (1000, 4.0, 165)])
    row = pt.test_from_activity(session, act, "run_30min")
    assert row.status == "failed" and row.confidence == "baja"
    assert next(c for c in row.checks if c["key"] == "duracion")["critical"]
    with pytest.raises(pt.TestError):
        pt.confirm(session, row)


def test_ritmo_irregular_baja_la_confianza(session: Session, user: User):
    act = _activity(session, user, [(900, 3.0, 130), (600, 4.6, 168), (600, 4.0, 170), (600, 3.3, 165)])
    row = pt.test_from_activity(session, act, "run_30min")
    regular = next(c for c in row.checks if c["key"] == "regularidad")
    assert not regular["ok"] and "varió" in regular["message"]
    assert row.status == "detected" and row.confidence in ("media", "baja")


def test_cooper_vo2max(session: Session, user: User):
    act = _activity(session, user, [(600, 3.0, 130), (720, 4.0, 175), (300, 2.5, 120)])
    row = pt.test_from_activity(session, act, "cooper")
    assert row.results["distance_m"] == 2880
    assert row.results["vo2max"] == pytest.approx((2880 - 504.9) / 44.73, abs=0.1)


def test_contrarreloj_5k(session: Session, user: User):
    act = _activity(session, user, [(600, 3.0, 130), (1250, 4.0, 175), (300, 2.5, 120)])
    row = pt.test_from_activity(session, act, "tt_5k")
    assert row.results["time_s"] == pytest.approx(1250, abs=2)
    assert 40 < row.results["vdot"] < 50
    assert row.results["threshold_pace_s_km"] > 250  # el ritmo T es más lento que el de 5K


def test_velocidad_critica(session: Session, user: User):
    act = _activity(session, user, [(600, 3.0, 130), (180, 5.0, 178), (1200, 2.5, 130), (720, 4.2, 176),
                                    (300, 2.5, 120)])  # fmt: skip
    row = pt.test_from_activity(session, act, "critical_speed")
    cs = (4.2 * 720 - 5.0 * 180) / 540
    assert row.results["cs_speed"] == pytest.approx(cs, abs=0.01)
    assert row.results["threshold_pace_s_km"] == round(1000 / (cs * 0.96))
    assert row.results["d_prime_m"] > 0


def test_fc_maxima_filtra_picos(session: Session, user: User):
    act = _activity(session, user, [(600, 3.0, 150), (15, 3.5, 191), (600, 3.0, 150)], spike=True)
    row = pt.test_from_activity(session, act, "max_hr")
    assert row.results["hr_max"] == 191  # el pico aislado de 225 no cuenta


def test_bici_fc_umbral_y_zonas(session: Session, user: User):
    act = _activity(session, user, [(900, 7.0, 120), (1800, 9.0, 158), (600, 6.0, 115)], sport="cycling")
    row = pt.test_from_activity(session, act, "bike_hr_30min")
    assert row.results["lthr"] == 158
    assert [z["name"] for z in row.results["hr_zones"]][0] == "Z1 Recuperación"
    # La FC umbral de bici no cambia las zonas de carrera.
    pt.confirm(session, row)
    assert estimate_thresholds(session, user.id)["lthr_source"] != "test"


def test_protocolo_de_otro_deporte(session: Session, user: User):
    act = _activity(session, user, THIRTY)
    with pytest.raises(pt.TestError, match="otro deporte"):
        pt.test_from_activity(session, act, "bike_hr_30min")
    with pytest.raises(pt.TestError):
        pt.test_from_activity(session, act, "manual")


def test_api_marcar_confirmar_y_borrar(client, user, session):
    act = _activity(session, user, THIRTY)
    h = auth(user)
    assert client.get(f"/api/v1/activities/{act.id}/test", headers=h).json() is None
    protocols = client.get("/api/v1/tests/protocols", headers=h).json()
    assert {"run_30min", "cooper", "bike_hr_30min", "manual"} <= {p["key"] for p in protocols}
    assert next(p for p in protocols if p["key"] == "run_30min")["template"][1]["duration_s"] == 1800

    res = client.post(f"/api/v1/activities/{act.id}/test", json={"protocol": "run_30min"}, headers=h)
    assert res.status_code == 200, res.text
    test = res.json()
    assert test["protocol_label"] == "30 min a tope" and test["summary"].startswith("FC umbral 170")
    # Otra persona no lo ve ni lo confirma.
    other = User(email="otra@example.com", password_hash="x")
    session.add(other)
    session.commit()
    assert client.post(f"/api/v1/tests/{test['id']}/confirm", headers=auth(other)).status_code == 404
    assert client.post(f"/api/v1/tests/{test['id']}/confirm", headers=h).json()["status"] == "confirmed"
    again = client.post(f"/api/v1/activities/{act.id}/test", json={"protocol": "run_20min"}, headers=h)
    assert again.status_code == 409
    assert client.get("/api/v1/progress/zones", headers=h).json()["current"]["thresholds"]["pace_source"] == "test"
    assert client.delete(f"/api/v1/tests/{test['id']}", headers=h).status_code == 204
    assert client.get("/api/v1/tests", headers=h).json() == []
    assert client.get("/api/v1/progress/zones", headers=h).json()["current"]["thresholds"]["pace_source"] != "test"


def test_api_resultado_manual(client, user, session):
    h = auth(user)
    bad = client.post("/api/v1/tests", json={"sport": "running", "test_date": DAY.isoformat(), "lthr": 300}, headers=h)
    assert bad.status_code == 422
    empty = client.post("/api/v1/tests", json={"sport": "running", "test_date": DAY.isoformat()}, headers=h)
    assert empty.status_code == 422
    res = client.post(
        "/api/v1/tests",
        json={"sport": "running", "test_date": DAY.isoformat(), "lthr": 168, "threshold_pace_s_km": 262,
              "hr_max": 193, "notes": "Informe del club"},
        headers=h,
    )  # fmt: skip
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "confirmed" and res.json()["protocol"] == "manual"
    thr = estimate_thresholds(session, user.id)
    assert (thr["lthr"], thr["threshold_pace_s_km"]) == (168, 262)
    assert prog.user_thresholds(session, user.id).hr_max == 193


def test_sesion_de_test_planificada_se_analiza_sola(client, user, session):
    act = _activity(session, user, THIRTY)
    h = auth(user)
    template = pt.PROTOCOLS["run_30min"].template
    res = client.post(
        "/api/v1/plans",
        json={"day": DAY.isoformat(), "sport": "running", "title": "Test 30 min", "blocks": template,
              "test_protocol": "run_30min"},
        headers=h,
    )  # fmt: skip
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["session_kind"] == "test" and body["test_protocol"] == "run_30min"
    assert body["activity_id"] == act.id
    row = session.exec(select(PerformanceTest).where(PerformanceTest.activity_id == act.id)).one()
    assert row.source == "planned" and row.status == "detected"
    assert row.planned_session_id == body["id"]
    # Volver a guardar la sesión no crea otro test.
    client.put(f"/api/v1/plans/{body['id']}", json={**res.json(), "blocks": template}, headers=h)
    assert len(session.exec(select(PerformanceTest)).all()) == 1
    bad = client.post("/api/v1/plans", json={"day": DAY.isoformat(), "sport": "running", "title": "x",
                                              "test_protocol": "inventado"}, headers=h)  # fmt: skip
    assert bad.status_code == 422


def test_detect_planned_tras_sincronizar(session: Session, user: User, monkeypatch):
    planned = PlannedSession(user_id=user.id, day=DAY, sport="running", title="Test", test_protocol="cooper",
                             session_kind="test")  # fmt: skip
    session.add(planned)
    session.commit()
    sent: list = []
    monkeypatch.setattr("app.services.notifications.notify", lambda *a, **k: sent.append(a) or True)
    from app.services.plan_service import match_pending

    _activity(session, user, [(600, 3.0, 130), (720, 4.0, 175), (300, 2.5, 120)])
    assert match_pending(session, user.id) == 1
    row = session.exec(select(PerformanceTest)).one()
    assert row.protocol == "cooper" and row.results["vo2max"] > 50
    assert sent and sent[0][2] == "test" and "VO2max" in sent[0][5]
