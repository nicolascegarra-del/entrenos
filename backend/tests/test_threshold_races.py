from datetime import UTC, date, datetime, timedelta

import pytest
from sqlmodel import Session, select

from app.core.security import create_token
from app.models import Activity, DailyMetric, User
from app.services import race_forecast, zones
from app.services.garmin_parser import parse_summary
from app.services.race_models import daniels_paces

TODAY = date.today()


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def _act(session: Session, user: User, days_ago: int, km: float, seconds: float, race: bool = False,
         metrics: dict | None = None) -> Activity:  # fmt: skip
    a = Activity(user_id=user.id, sport="running", start_time=datetime.now(UTC) - timedelta(days=days_ago),
                 duration_s=seconds, moving_duration_s=seconds, distance_m=km * 1000, avg_hr=150, is_race=race,
                 metrics=metrics or {})  # fmt: skip
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


def _lt(speed: float, day: date = TODAY, hr: int = 165) -> dict:
    return {"speed_and_heart_rate": {"speed": speed, "heartRate": hr, "calendarDate": day.isoformat()}}


# ─── Umbral de Garmin ────────────────────────────────────────────────────────


@pytest.mark.parametrize(("raw", "speed"), [(0.308, 3.08), (3.08, 3.08), (0.1, None), (9.5, None), (None, None)])
def test_velocidad_umbral_de_garmin_en_ambas_unidades(raw, speed):
    assert zones.normalize_lt_speed(raw) == speed


def test_guarda_y_lee_el_umbral_de_garmin(session, user):
    assert zones.store_garmin_threshold(session, user.id, _lt(0.25)) is True  # 2,5 m/s → 400 s/km
    assert zones.garmin_threshold(session, user.id, TODAY) == (400, TODAY)
    row = session.exec(select(DailyMetric).where(DailyMetric.user_id == user.id)).one()
    assert row.metrics == {"lt_speed": 2.5, "lt_hr": 165}
    assert zones.store_garmin_threshold(session, user.id, {}) is False


def test_umbral_de_garmin_antiguo_no_cuenta(session, user):
    zones.store_garmin_threshold(session, user.id, _lt(0.3, TODAY - timedelta(days=400)))
    assert zones.garmin_threshold(session, user.id, TODAY) is None


def test_garmin_es_la_fuente_prioritaria(session, user):
    _act(session, user, 20, 10, 2700, metrics={"best_10k": 2700})  # VDOT ~ 36 → T ~ 4:55
    zones.store_garmin_threshold(session, user.id, _lt(0.30))  # 333 s/km, más lento que Daniels T
    t = zones.estimate_thresholds(session, user.id)
    assert t["pace_source"] == "garmin" and t["threshold_pace_s_km"] == 333
    assert {"garmin", "vdot"} <= t["candidates"].keys() and t["candidates"]["vdot"] < 333


# ─── Ritmos de entrenamiento coherentes con el umbral ────────────────────────


def test_vdot_equivalente_a_un_umbral():
    fast, slow = daniels_paces(42)["threshold"]
    assert zones.vdot_for_threshold((fast + slow) / 2) == pytest.approx(42, abs=0.3)  # Daniels redondea a segundos
    assert zones.vdot_for_threshold(30) is None  # fuera de rango


def test_ritmos_desde_el_umbral_si_es_mas_rapido(session, user):
    _act(session, user, 20, 10, 4200, metrics={"best_10k": 4200})  # marcas de entreno flojas (VDOT ~ 22)
    zones.store_garmin_threshold(session, user.id, _lt(0.30))  # 5:33 /km de umbral
    eff = zones.effective_paces(session, user.id)
    assert eff["basis"] == "umbral" and eff["vdot"] > eff["vdot_marks"]
    t_mid = sum(eff["paces"]["threshold"]) / 2
    assert t_mid == pytest.approx(333, abs=2)  # los ritmos T coinciden con el umbral efectivo
    assert eff["threshold_source"] == "garmin" and "garmin" in eff["alternatives"]


def test_sin_datos_no_hay_ritmos(session, user):
    assert zones.effective_paces(session, user.id) is None


# ─── Carreras a tope ─────────────────────────────────────────────────────────


def test_si_hay_carreras_solo_cuentan_ellas(session, user):
    _act(session, user, 40, 10, 3600, metrics={"best_10k": 3600, "best_5k": 1750})  # entreno
    _act(session, user, 30, 15, 4200, race=True, metrics={"best_10k": 2750})  # carrera de 15 km
    data = race_forecast.training_data(race_forecast.prog.user_activities(session, user.id), TODAY)
    assert data.from_races and "best_5k" not in data.efforts
    assert data.efforts["best_10k"][1] == 2750 and any(k.startswith("race_") for k in data.efforts)
    f = race_forecast.forecast(10000, data)
    assert f.source_is_race and not any("entrenamiento, no carreras" in w for w in f.warnings)


def test_sin_carreras_usa_las_marcas_de_entreno(session, user):
    _act(session, user, 40, 10, 3600, metrics={"best_10k": 3600})
    data = race_forecast.training_data(race_forecast.prog.user_activities(session, user.id), TODAY)
    assert not data.from_races
    assert any("entrenamiento, no carreras" in w for w in race_forecast.forecast(10000, data).warnings)


def test_garmin_race_marca_la_actividad():
    base = {"activityId": 1, "startTimeGMT": "2026-10-01 08:00:00", "duration": 3000,
            "activityType": {"typeKey": "running"}}  # fmt: skip
    assert parse_summary({**base, "eventType": {"typeKey": "race"}}).is_race is True
    assert parse_summary({**base, "eventType": {"typeKey": "uncategorized"}}).is_race is False


# ─── API ─────────────────────────────────────────────────────────────────────


def test_api_marcar_carrera_y_ritmos(client, user, session):
    a = _act(session, user, 20, 10, 3000, metrics={"best_10k": 3000})
    res = client.put(f"/api/v1/activities/{a.id}/race", json={"is_race": True}, headers=auth(user))
    assert res.json() == {"activity_id": a.id, "is_race": True}
    assert client.get(f"/api/v1/activities/{a.id}", headers=auth(user)).json()["is_race"] is True
    paces = client.get("/api/v1/training-paces", headers=auth(user)).json()
    assert paces["basis"] in ("marcas", "umbral") and paces["vdot_from_races"] is True
    assert "vdot" in paces["alternatives"] and paces["paces"]["threshold"][0] > 0
    other = User(email="otra@example.com", password_hash="x")
    session.add(other)
    session.commit()
    assert client.put(f"/api/v1/activities/{a.id}/race", json={"is_race": False},
                      headers=auth(other)).status_code == 404  # fmt: skip


def test_api_ritmos_sin_datos(client, user):
    data = client.get("/api/v1/training-paces", headers=auth(user)).json()
    assert data["paces"] is None and data["basis"] is None


def test_zonas_guardadas_reciben_las_alternativas(session, user):
    _act(session, user, 20, 10, 2700, metrics={"best_10k": 2700})
    row = zones.refresh_zones(session, user.id)
    row.thresholds = {k: v for k, v in row.thresholds.items() if k != "candidates"}  # zonas de antes
    session.add(row)
    session.commit()
    again = zones.refresh_zones(session, user.id)
    assert again.id == row.id and "vdot" in again.thresholds["candidates"]
