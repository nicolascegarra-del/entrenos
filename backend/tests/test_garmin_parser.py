import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

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
