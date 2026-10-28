import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlmodel import select

from app.services.garmin_parser import (
    TIME_CHANNEL,
    get_path,
    parse_daily,
    parse_details,
    parse_laps,
    parse_summary,
)

FIXTURES = Path(__file__).parent / "fixtures" / "garmin"


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("obj", "path", "expected"),
    [
        ({"a": {"b": 1}}, "a.b", 1),
        ([{"x": {"y": 2}}], "0.x.y", 2),
        ([], "0.x", None),
        ({"a": None}, "a.b", None),
        ({"a": [1]}, "a.foo", None),
    ],
)
def test_get_path_cuando_ruta_variada_entonces_resuelve_o_none(obj, path, expected):
    assert get_path(obj, path) == expected


def test_parse_summary_cuando_carrera_735xt_entonces_columnas_y_metricas_del_catalogo():
    parsed = parse_summary(load("activity_summary"))
    assert parsed.garmin_activity_id == 9000000001
    assert parsed.garmin_device_id == 1000000001
    assert parsed.sport == "running"
    assert parsed.start_time == datetime(2026, 10, 14, 15, 58, 5, tzinfo=UTC)
    assert parsed.timezone == "+02:00"
    assert parsed.distance_m == pytest.approx(6009.75)
    assert parsed.avg_hr == 133
    assert parsed.metrics["avg_cadence"] > 150
    assert "aerobic_te" in parsed.metrics
    # El 735XT no mide potencia: no debe aparecer la métrica.
    assert "avg_power" not in parsed.metrics


def test_parse_summary_cuando_reloj_con_potencia_entonces_aparece_sin_cambiar_codigo():
    summary = load("activity_summary") | {"avgPower": 265.0, "normPower": 280.0}
    metrics = parse_summary(summary).metrics
    assert metrics["avg_power"] == 265.0
    assert metrics["normalized_power"] == 280.0


def test_parse_summary_cuando_zona_horaria_negativa_entonces_offset_con_signo():
    summary = load("activity_summary") | {
        "startTimeGMT": "2026-10-14 15:00:00",
        "startTimeLocal": "2026-10-14 10:30:00",
    }
    assert parse_summary(summary).timezone == "-04:30"


def test_parse_details_cuando_detalle_garmin_entonces_canales_de_catalogo_alineados():
    channels = parse_details(load("activity_details"))
    assert {"time", "hr", "speed", "lat", "lon", "altitude", "distance", "cadence"} <= channels.keys()
    lengths = {len(v) for v in channels.values()}
    assert lengths == {60}
    assert channels[TIME_CHANNEL][0] == 0
    assert channels[TIME_CHANNEL][-1] > 0
    # Potencia acumulada = 65535 (centinela) en todo el detalle: canal descartado.
    assert "sumAccumulatedPower" not in channels


def test_parse_details_cuando_sensor_desconocido_entonces_se_conserva_con_nombre_garmin():
    details = {
        "metricDescriptors": [
            {"metricsIndex": 0, "key": "directTimestamp"},
            {"metricsIndex": 1, "key": "directCoreTemperature"},
        ],
        "activityDetailMetrics": [{"metrics": [1000.0, 37.2]}, {"metrics": [2000.0, 37.4]}],
    }
    channels = parse_details(details)
    assert channels == {"time": [0.0, 1.0], "directCoreTemperature": [37.2, 37.4]}


def test_parse_details_cuando_sin_detalle_entonces_vacio():
    assert parse_details(None) == {}
    assert parse_details({"activityDetailMetrics": []}) == {}


def test_parse_laps_cuando_splits_entonces_offset_y_metricas_extra():
    start = datetime(2026, 10, 14, 15, 58, 5, tzinfo=UTC)
    laps = parse_laps(load("activity_splits"), start)
    assert len(laps) >= 1
    first = laps[0]
    assert first["index"] == 0
    assert first["start_offset_s"] == 0
    assert first["avg_hr"] == 133
    assert first["metrics"]["avg_cadence"] > 150
    assert "avg_power" not in first["metrics"]


def test_parse_laps_cuando_segunda_vuelta_entonces_offset_relativo_al_inicio():
    start = datetime(2026, 10, 14, 10, 0, 0, tzinfo=UTC)
    splits = {
        "lapDTOs": [
            {"startTimeGMT": "2026-10-14T10:00:00.0", "duration": 300.0},
            {"startTimeGMT": "2026-10-14T10:05:00.0", "duration": 240.0, "averagePower": 250.0},
        ]
    }
    laps = parse_laps(splits, start)
    assert [lap["start_offset_s"] for lap in laps] == [0, 300]
    assert laps[1]["metrics"] == {"avg_power": 250.0}


def test_parse_daily_cuando_735xt_entonces_metricas_disponibles_y_sin_hrv():
    metrics = parse_daily(load("daily"))
    assert metrics["resting_hr"] > 30
    assert metrics["vo2max_running"] == 44.0
    assert metrics["steps_daily"] > 0
    assert "sleep_seconds" not in metrics  # ese día el reloj no registró sueño
    assert "hrv_last_night" not in metrics


def test_parse_daily_cuando_reloj_nuevo_con_hrv_entonces_aparece():
    raw = load("daily") | {"hrv": {"hrvSummary": {"lastNightAvg": 62}}}
    assert parse_daily(raw)["hrv_last_night"] == 62


def test_get_path_cuando_alternativas_entonces_primera_con_valor():
    assert get_path({"b": 2}, "a|b") == 2
    assert get_path({"a": 1, "b": 2}, "a|b") == 1
    assert get_path({}, "a|b") is None


def test_parse_details_cuando_carrera_entonces_cadencia_en_pasos_totales_por_minuto():
    channels = parse_details(load("activity_details"))
    cadence = [v for v in channels["cadence"] if v]
    assert sum(cadence) / len(cadence) > 120  # directDoubleCadence (~160), no la de una pierna (~80)
    assert "directRunCadence" in channels  # la alternativa no elegida se conserva con su nombre


def test_parse_details_cuando_bici_entonces_cadencia_rpm():
    details = {
        "metricDescriptors": [
            {"metricsIndex": 0, "key": "directTimestamp"},
            {"metricsIndex": 1, "key": "directBikeCadence"},
        ],
        "activityDetailMetrics": [{"metrics": [0.0, 88.0]}, {"metrics": [1000.0, 90.0]}],
    }
    assert parse_details(details)["cadence"] == [88.0, 90.0]


def test_parse_daily_cuando_reloj_con_estres_body_battery_y_fases_entonces_aparecen():
    raw = load("daily")
    raw["stats"] = {
        **(raw.get("stats") or {}),
        "averageStressLevel": 31,
        "maxStressLevel": 88,
        "restStressDuration": 30000,
        "lowStressDuration": 12000,
        "mediumStressDuration": 6000,
        "highStressDuration": 1800,
        "bodyBatteryHighestValue": 92,
        "bodyBatteryLowestValue": 18,
        "bodyBatteryAtWakeTime": 85,
        "averageSpo2": 95,
        "lowestSpo2": 89,
        "moderateIntensityMinutes": 20,
        "vigorousIntensityMinutes": 35,
        "floorsAscended": 7,
    }
    raw["sleep"] = {
        "dailySleepDTO": {
            "sleepTimeSeconds": 27000,
            "deepSleepSeconds": 5400,
            "remSleepSeconds": 6300,
            "lightSleepSeconds": 15300,
            "awakeSleepSeconds": 900,
            "avgSleepStress": 14,
            "averageRespirationValue": 14.5,
        }
    }
    raw["hrv"] = {"hrvSummary": {"lastNightAvg": 58, "weeklyAvg": 61}}
    raw["training_readiness"] = [{"score": 72}]
    m = parse_daily(raw)
    assert (m["stress_avg"], m["stress_max"], m["stress_high_s"], m["stress_rest_s"]) == (31, 88, 1800, 30000)
    assert (m["body_battery_max"], m["body_battery_min"], m["body_battery_wake"]) == (92, 18, 85)
    assert (m["spo2_avg"], m["spo2_lowest"]) == (95, 89)
    assert (m["sleep_deep_s"], m["sleep_rem_s"], m["sleep_light_s"], m["sleep_awake_s"]) == (5400, 6300, 15300, 900)
    assert m["sleep_stress_avg"] == 14 and m["breath_rate"] == 14.5
    assert m["hrv_weekly_avg"] == 61 and m["training_readiness"] == 72
    assert m["intensity_min_vigorous"] == 35 and m["floors_ascended"] == 7


def test_parse_daily_cuando_reloj_sin_esos_datos_entonces_no_se_inventan():
    raw = load("daily")
    raw["stats"] = {**(raw.get("stats") or {}), "averageStressLevel": None, "bodyBatteryHighestValue": None}
    m = parse_daily(raw)
    assert not {"stress_avg", "stress_max", "body_battery_max", "training_readiness"} & set(m)


def test_parse_summary_cuando_reloj_con_potencia_y_dinamica_entonces_metricas_extra():
    from app.services.garmin_parser import parse_summary

    summary = {
        "activityId": 1,
        "startTimeGMT": "2026-10-20 07:00:00",
        "duration": 3600,
        "activityType": {"typeKey": "running"},
        "avgPower": 260,
        "maxPower": 512,
        "avgVerticalOscillation": 8.9,
        "avgGroundContactTime": 245,
        "avgVerticalRatio": 7.6,
        "maxTemperature": 24,
        "waterEstimated": 650,
        "avgRespirationRate": 38,
    }
    metrics = parse_summary(summary).metrics
    assert metrics["max_power"] == 512 and metrics["avg_power"] == 260
    assert metrics["avg_vertical_oscillation"] == 8.9 and metrics["avg_ground_contact_time"] == 245
    assert metrics["max_temperature"] == 24 and metrics["sweat_loss_ml"] == 650


def test_reparse_garmin_daily_cuando_raw_guardado_entonces_rellena_lo_nuevo(session, user):
    from datetime import date

    from app.models import DailyMetric
    from app.services.sync_service import reparse_garmin_daily

    raw = {"stats": {"restingHeartRate": 50, "maxStressLevel": 70, "averageStressLevel": 25}}
    session.add(DailyMetric(user_id=user.id, day=date(2026, 10, 1), metrics={"resting_hr": 50}, raw=raw))
    session.commit()
    assert reparse_garmin_daily(session) == 1
    row = session.exec(select(DailyMetric).where(DailyMetric.user_id == user.id)).one()
    assert row.metrics["stress_max"] == 70 and row.metrics["stress_avg"] == 25 and row.metrics["resting_hr"] == 50
