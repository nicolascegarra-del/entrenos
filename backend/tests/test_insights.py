from datetime import UTC, date, datetime, timedelta

import pytest
from sqlmodel import Session

from app.core.security import create_token
from app.models import Activity, DailyMetric, User
from app.services import insights as ins
from app.services import race_models as rm


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def points(ctl_values: list[float], tsb: float = 0) -> list[dict]:
    return [{"ctl": c, "tsb": tsb, "atl": c} for c in ctl_values]


# ─── Cálculos ───────────────────────────────────────────────────────────────


def test_vdot_cuando_5k_en_20_min_entonces_aprox_50_como_tablas_de_daniels():
    assert rm.vdot(5000, 20 * 60) == pytest.approx(49.8, abs=0.5)


def test_pace_at_fraction_cuando_vdot_50_entonces_ritmos_de_daniels():
    assert rm.pace_at_fraction(50, 0.86) == pytest.approx(255, abs=8)  # umbral ≈ 4:15 /km
    assert rm.pace_at_fraction(50, 0.975) == pytest.approx(235, abs=8)  # intervalos ≈ 3:55 /km
    easy_fast, easy_slow = rm.pace_at_fraction(50, 0.74), rm.pace_at_fraction(50, 0.59)
    assert 280 < easy_fast < easy_slow < 360


def test_riegel_cuando_5k_20_min_entonces_10k_aprox_41_40():
    assert rm.riegel(1200, 5000, 10000) == pytest.approx(2501, abs=2)


def test_acwr_series_cuando_carga_constante_entonces_cerca_de_1():
    start = date(2026, 1, 1)
    loads = {start + timedelta(days=i): 60.0 for i in range(120)}
    series = ins.acwr_series(loads, start + timedelta(days=100), start + timedelta(days=119))
    assert series[-1]["acwr"] == pytest.approx(1.0, abs=0.05)


def test_acwr_series_cuando_pico_reciente_entonces_mayor_que_1_5():
    start = date(2026, 1, 1)
    loads = {start + timedelta(days=i): 40.0 for i in range(60)}
    loads |= {start + timedelta(days=60 + i): 150.0 for i in range(7)}
    series = ins.acwr_series(loads, start + timedelta(days=60), start + timedelta(days=66))
    assert series[-1]["acwr"] > 1.5


def test_decoupling_cuando_fc_sube_en_la_segunda_mitad_entonces_porcentaje():
    n = 200
    channels = {
        "time": [float(i * 10) for i in range(n)],
        "speed": [3.0] * n,
        "hr": [140.0] * (n // 2) + [147.0] * (n // 2),
    }
    assert ins.decoupling_pct(channels) == pytest.approx(4.8, abs=0.2)
    assert ins.decoupling_pct({"time": [0.0], "speed": [3.0], "hr": [140.0]}) is None


def test_intensity_split_cuando_zonas_entonces_agrupa_baja_media_alta():
    a = Activity(user_id=1, sport="running", start_time=datetime.now(UTC), duration_s=3600,
                 metrics={"hr_zone_1_s": 600, "hr_zone_2_s": 1800, "hr_zone_3_s": 600, "hr_zone_4_s": 500,
                          "hr_zone_5_s": 100})  # fmt: skip
    assert ins.intensity_split([a]) == {"low": 2400, "moderate": 600, "high": 600}


# ─── Reglas ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("ctl", "tsb", "status"),
    [
        ([40] * 7 + [50], 0, "alert"),  # +10/semana
        ([40] * 8, -35, "alert"),  # fatiga alta
        ([40] * 7 + [35], 5, "watch"),  # perdiendo fitness
        ([40] * 7 + [44], -5, "good"),  # progresión sostenible
        ([40] * 8, 2, "info"),
    ],
)
def test_fitness_insight_cuando_rampa_y_forma_entonces_estado(ctl, tsb, status):
    assert ins.fitness_insight(points(ctl, tsb)).status == status


@pytest.mark.parametrize(("acwr", "status"), [(1.7, "alert"), (1.4, "watch"), (0.6, "watch"), (1.05, "good")])
def test_acwr_insight_cuando_ratio_entonces_estado(acwr, status):
    assert ins.acwr_insight([{"day": date.today(), "acwr": acwr}]).status == status


@pytest.mark.parametrize(("last_km", "status"), [(40, "alert"), (28, "good"), (21, "info"), (10, "info")])
def test_volume_insight_cuando_cambio_semanal_entonces_estado(last_km, status):
    weeks = [{"distance_m": 25000}] * 4 + [{"distance_m": last_km * 1000}, {"distance_m": 0}]  # la última en curso
    assert ins.volume_insight(weeks).status == status


@pytest.mark.parametrize(
    ("split", "status", "title"),
    [
        ({"low": 8000, "moderate": 1000, "high": 1000}, "good", "Base suave sólida"),
        ({"low": 5000, "moderate": 4000, "high": 1000}, "watch", "Mucho tiempo en zona media"),
        ({"low": 6000, "moderate": 2000, "high": 2000}, "watch", "Poca intensidad baja"),
        ({"low": 600, "moderate": 0, "high": 0}, "nodata", "Distribución de intensidad"),
    ],
)
def test_intensity_insight_cuando_distribucion_entonces_estado(split, status, title):
    result = ins.intensity_insight(split)
    assert (result.status, result.title) == (status, title)


@pytest.mark.parametrize(("recent", "status"), [(58, "alert"), (55, "watch"), (52, "good")])
def test_resting_hr_insight_cuando_sube_sobre_referencia_entonces_estado(recent, status):
    series = [{"value": 52.0}] * 20 + [{"value": float(recent)}] * 3
    assert ins.resting_hr_insight(series).status == status


@pytest.mark.parametrize(("end", "status"), [(46, "good"), (42, "watch"), (44.3, "info")])
def test_vo2max_insight_cuando_tendencia_entonces_estado(end, status):
    series = [{"value": 44.0}] * 3 + [{"value": float(end)}] * 3
    assert ins.vo2max_insight(series).status == status


def test_recovery_insight_cuando_poco_sueno_y_fc_alta_entonces_alerta():
    rhr_alta = ins.Insight("alert", "", "")
    assert ins.recovery_insight([6.0] * 7, rhr_alta).status == "alert"
    assert ins.recovery_insight([6.0] * 7, ins.Insight("good", "", "")).status == "watch"
    assert ins.recovery_insight([7.5] * 7, rhr_alta).status == "good"


@pytest.mark.parametrize(("weeks", "status"), [([3, 4, 3, 3], "good"), ([2, 0, 2, 2], "info"), ([1, 0, 0, 1], "watch")])
def test_consistency_insight_cuando_regularidad_entonces_estado(weeks, status):
    assert ins.consistency_insight(weeks, None).status == status


def test_strength_insight_cuando_sin_registros_entonces_recomendacion():
    assert ins.strength_insight([], 0).status == "info"
    overview = [{"exercise": "Sentadilla", "e1rm_change_kg": 5.0}]
    assert ins.strength_insight(overview, 8).status == "good"
    assert ins.strength_insight(overview, 2).status == "watch"


def test_overall_cuando_un_grupo_tiene_alerta_entonces_semaforo_rojo_en_ese_grupo():
    sections = {
        "fitness": ins.Insight("good", "Bien", ""),
        "acwr": ins.Insight("alert", "Pico de carga", ""),
        "recovery": ins.Insight("info", "Ok", ""),
        "consistency": ins.Insight("nodata", "", ""),
    }
    by_label = {g["label"]: g for g in ins.overall(sections)}
    assert by_label["Carga"]["status"] == "alert" and by_label["Carga"]["title"] == "Pico de carga"
    assert by_label["Recuperación"]["status"] == "good"
    assert by_label["Constancia"]["status"] == "nodata"


# ─── API ────────────────────────────────────────────────────────────────────


def test_api_insights_cuando_historial_entonces_secciones_y_extras(client, session: Session, user: User):
    today = date.today()
    for i in range(0, 60, 2):
        day = today - timedelta(days=i)
        session.add(Activity(
            user_id=user.id, sport="running", timezone="+02:00",
            start_time=datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=8),
            duration_s=3000, distance_m=8000 + i * 10, avg_hr=145,
            metrics={"vo2max": 44 + i / 30, "best_5k": 1500.0 + i, "hr_zone_2_s": 2400, "hr_zone_4_s": 300},
        ))  # fmt: skip
    for i in range(20):
        metrics = {"resting_hr": 52, "sleep_seconds": 26000}
        session.add(DailyMetric(user_id=user.id, day=today - timedelta(days=i), metrics=metrics))
    session.commit()

    res = client.get("/api/v1/progress/insights?days=90", headers=auth(user))
    assert res.status_code == 200
    data = res.json()
    assert {g["label"] for g in data["overall"]} == {"Carga", "Recuperación", "Constancia", "Tendencia aeróbica"}
    expected = {"fitness", "acwr", "volume", "intensity", "resting_hr", "vo2max", "efficiency", "records",
                "recovery", "consistency", "strength"}  # fmt: skip
    assert set(data["sections"]) == expected
    assert all(s["status"] in {"good", "watch", "alert", "info", "nodata"} for s in data["sections"].values())
    assert data["sections"]["intensity"]["status"] == "good"
    assert data["sections"]["records"]["evidence"][0]["label"].startswith("Riegel")
    assert [p["label"] for p in data["predictions"]] == ["5 km", "10 km", "Media maratón", "Maratón"]
    assert data["training_paces"]["threshold"] < data["training_paces"]["easy"][0]
    assert data["acwr"] and "no sustituye" in data["disclaimer"]


def test_api_insights_cuando_usuario_sin_datos_entonces_nodata_sin_error(client, user):
    data = client.get("/api/v1/progress/insights", headers=auth(user)).json()
    assert data["sections"]["fitness"]["status"] == "nodata"
    assert data["predictions"] == [] and data["training_paces"] is None


def test_is_steady_cuando_series_entonces_no_y_rodaje_si():
    rodaje = {"speed": [3.0, 3.1, 2.9, 3.05] * 10}
    series = {"speed": [4.5, 4.6, 1.5, 1.4] * 10}
    assert ins.is_steady(rodaje) is True
    assert ins.is_steady(series) is False
    assert ins.is_steady({"speed": [3.0] * 5}) is False


def test_volume_insight_cuando_baja_moderada_entonces_no_dice_progresivo():
    weeks = [{"distance_m": 16800}] * 4 + [{"distance_m": 14100}, {"distance_m": 0}]
    result = ins.volume_insight(weeks)
    assert result.title.startswith("Volumen algo menor")


def test_mensajes_cuando_decimales_entonces_coma_espanola():
    result = ins.acwr_insight([{"day": date.today(), "acwr": 1.22}])
    assert result.title == "Carga equilibrada (ACWR 1,22)"
    assert ins._n(3.0, 0, sign=True) == "+3"
