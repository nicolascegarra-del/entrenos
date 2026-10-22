from datetime import UTC, date, datetime, timedelta

import pytest
from sqlmodel import Session, select

from app.core.security import create_token
from app.models import Activity, ActivityStream, AthleteZones, User
from app.services import pace_curve, zones


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def _run(session: Session, user: User, days_ago: int, segments: list[tuple[int, float]], lthr: float | None = None):
    """Carrera con series de 1 Hz: segmentos (segundos, velocidad m/s)."""
    time, distance, t, d = [], [], 0.0, 0.0
    for seconds, speed in segments:
        for _ in range(seconds):
            time.append(t)
            distance.append(d)
            t += 1
            d += speed
    a = Activity(user_id=user.id, sport="running", start_time=datetime.now(UTC) - timedelta(days=days_ago),
                 duration_s=t, distance_m=d, avg_hr=150, metrics={"lthr": lthr} if lthr else {})  # fmt: skip
    session.add(a)
    session.flush()
    session.add(ActivityStream(activity_id=a.id, channel="time", values=time))
    session.add(ActivityStream(activity_id=a.id, channel="distance", values=distance))
    session.commit()
    return a


# ─── Curva de ritmos ─────────────────────────────────────────────────────────


def test_best_speeds_encuentra_el_tramo_rapido():
    time = list(range(3601))
    distance = [3.0 * t for t in range(3601)]
    for t in range(1000, 1301):  # 5 min a 5 m/s
        distance[t] = distance[1000] + 5.0 * (t - 1000)
    for t in range(1301, 3601):
        distance[t] = distance[1300] + 3.0 * (t - 1300)
    curve = pace_curve.best_speeds(time, distance)
    assert curve[300] == pytest.approx(5.0) and curve[60] == pytest.approx(5.0)
    assert curve[3600] == pytest.approx((3.0 * 3300 + 5.0 * 300) / 3600, rel=1e-3)


def test_best_speeds_cuando_salto_de_gps_entonces_no_falsea_el_mejor_minuto():
    time = list(range(600))
    distance = [3.0 * t for t in range(600)]
    for t in range(300, 600):
        distance[t] += 400  # salto de 400 m en un segundo
    assert pace_curve.best_speeds(time, distance, durations=(60,))[60] < 3.2


def test_best_speeds_ignora_ventanas_con_huecos_y_duraciones_que_no_caben():
    time = [0, 1, 2, 500, 501]  # hueco de casi 500 s
    distance = [0, 4, 8, 2000, 2004]
    assert pace_curve.best_speeds(time, distance, durations=(60, 3600)) == {}


def test_critical_speed_recupera_cs_y_d_prima():
    cs, dp = 4.2, 180
    curve = {t: (cs * t + dp) / t for t in pace_curve.CS_DURATIONS_S}
    assert pace_curve.critical_speed(curve) == pytest.approx((4.2, 180), rel=1e-3)
    assert pace_curve.critical_speed({300: 4.0}) is None


def test_curva_se_guarda_en_la_actividad_y_api(client, user, session):
    a = _run(session, user, 10, [(600, 3.0), (300, 4.5), (600, 3.0)])
    _run(session, user, 250, [(1500, 3.2)])  # periodo anterior
    res = client.get("/api/v1/progress/pace-curve?days=180", headers=auth(user)).json()
    five = next(d for d in res["durations"] if d["seconds"] == 300)
    assert five["best"]["activity_id"] == a.id and five["best"]["pace_s_km"] == pytest.approx(222.2, abs=0.2)
    assert five["previous"]["pace_s_km"] == pytest.approx(312.5, abs=0.2)
    assert len(res["quarters"]) == 4
    session.expire_all()
    assert session.get(type(a), a.id).metrics["pace_curve"]["v"] == pace_curve.CURVE_VERSION


# ─── Zonas ───────────────────────────────────────────────────────────────────


def test_zonas_de_friel():
    hr = zones.hr_zones(170)
    assert hr[0] == {"name": "Z1 Recuperación", "min": 0, "max": 143} and hr[-1]["max"] is None
    pace = zones.pace_zones(300)
    assert pace[0]["fast"] == 387 and pace[0]["slow"] is None
    assert pace[3] == {"name": "Z4 Umbral", "fast": 297, "slow": 318}


def test_refresh_zones_guarda_historial_solo_si_cambia(session, user, monkeypatch):
    values = {"lthr": 165, "lthr_source": "garmin", "threshold_pace_s_km": 290, "pace_source": "vdot", "vdot": 45}
    monkeypatch.setattr(zones, "estimate_thresholds", lambda s, uid, today=None: dict(values))
    day1 = date(2026, 9, 1)
    zones.refresh_zones(session, user.id, day1)
    zones.refresh_zones(session, user.id, day1 + timedelta(days=5))  # sin cambios apreciables
    assert len(session.exec(select(AthleteZones)).all()) == 1
    values["threshold_pace_s_km"] = 280
    zones.refresh_zones(session, user.id, day1 + timedelta(days=10))
    rows = session.exec(select(AthleteZones).order_by(AthleteZones.valid_from)).all()
    assert len(rows) == 2 and rows[1].zones["pace"][3]["fast"] == round(280 * 0.99)
    report = zones.zones_report(session, user.id, day1 + timedelta(days=12))
    assert report["changed_recently"] and report["previous"]["thresholds"]["threshold_pace_s_km"] == 290


def test_api_zonas_con_lthr_de_garmin(client, user, session):
    _run(session, user, 5, [(1800, 3.3)], lthr=168)
    res = client.get("/api/v1/progress/zones", headers=auth(user)).json()
    assert res["current"]["thresholds"]["lthr"] == 168 and res["current"]["thresholds"]["lthr_source"] == "garmin"
    assert res["current"]["zones"]["hr"][3]["name"] == "Z4 Umbral"


def test_api_zonas_sin_datos(client, user):
    assert client.get("/api/v1/progress/zones", headers=auth(user)).json()["current"] is None


def test_umbral_de_ritmo_elige_la_estimacion_mas_rapida(session, user, monkeypatch):
    # Corre 1 h a 2,5 m/s (6:40 /km): el umbral no puede salir más lento aunque el VDOT sea bajo.
    _run(session, user, 3, [(3700, 2.5)], lthr=160)

    class F:
        vdot_current = 28.0

    monkeypatch.setattr(zones, "forecast", lambda distance, data: F())
    t = zones.estimate_thresholds(session, user.id)
    assert t["pace_source"] == "mejor_hora" and t["threshold_pace_s_km"] == 400


def test_la_curva_guardada_no_rompe_el_listado_de_actividades(client, user, session):
    _run(session, user, 3, [(900, 3.0)])
    client.get("/api/v1/progress/pace-curve", headers=auth(user))  # guarda la curva en metrics
    res = client.get("/api/v1/activities", headers=auth(user))
    assert res.status_code == 200 and "pace_curve" not in res.json()["items"][0]["metrics"]
    assert client.get("/api/v1/summary", headers=auth(user)).status_code == 200
