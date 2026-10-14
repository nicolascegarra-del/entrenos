"""
Catálogo inicial de métricas, basado en lo que devuelve un Forerunner 735XT
más las que traen relojes más recientes (potencia, HRV...). Añadir una métrica
nueva es añadir una entrada aquí y ejecutar `python -m app.cli seed-catalog`.
"""

from sqlmodel import Session

from app.models import MetricDefinition, MetricScope

RUN, BIKE, STRENGTH = "running", "cycling", "strength_training"

_A, _S, _D = MetricScope.ACTIVITY, MetricScope.STREAM, MetricScope.DAILY

CATALOG: list[MetricDefinition] = [
    # ── Actividad (agregados) ──────────────────────────────────────────────
    MetricDefinition(
        key="avg_speed",
        scope=_A,
        label="Velocidad media",
        unit="m/s",
        higher_is_better=True,
        sports=[RUN, BIKE],
        sources={"garmin_summary": "averageSpeed"},
    ),
    MetricDefinition(
        key="avg_cadence",
        scope=_A,
        label="Cadencia media",
        unit="ppm",
        sports=[RUN, BIKE],
        sources={"garmin_summary": "averageRunningCadenceInStepsPerMinute"},
    ),
    MetricDefinition(
        key="avg_stride_length",
        scope=_A,
        label="Longitud de zancada",
        unit="cm",
        sports=[RUN],
        sources={"garmin_summary": "avgStrideLength"},
    ),
    MetricDefinition(
        key="avg_power",
        scope=_A,
        label="Potencia media",
        unit="W",
        higher_is_better=True,
        sports=[RUN, BIKE],
        sources={"garmin_summary": "avgPower"},
    ),
    MetricDefinition(
        key="normalized_power",
        scope=_A,
        label="Potencia normalizada",
        unit="W",
        sports=[BIKE],
        sources={"garmin_summary": "normPower"},
    ),
    MetricDefinition(
        key="aerobic_te",
        scope=_A,
        label="Training Effect aeróbico",
        unit="",
        sources={"garmin_summary": "aerobicTrainingEffect"},
    ),
    MetricDefinition(
        key="anaerobic_te",
        scope=_A,
        label="Training Effect anaeróbico",
        unit="",
        sources={"garmin_summary": "anaerobicTrainingEffect"},
    ),
    MetricDefinition(
        key="training_load",
        scope=_A,
        label="Carga de entrenamiento",
        unit="",
        sources={"garmin_summary": "activityTrainingLoad"},
    ),
    MetricDefinition(
        key="steps", scope=_A, label="Pasos", unit="", sports=[RUN], sources={"garmin_summary": "steps"}
    ),
    MetricDefinition(
        key="total_sets",
        scope=_A,
        label="Series",
        unit="",
        sports=[STRENGTH],
        sources={"garmin_summary": "totalSets"},
    ),
    MetricDefinition(
        key="total_reps",
        scope=_A,
        label="Repeticiones",
        unit="",
        sports=[STRENGTH],
        sources={"garmin_summary": "totalReps"},
    ),
    # ── Streams (segundo a segundo) ────────────────────────────────────────
    MetricDefinition(
        key="hr",
        scope=_S,
        label="Frecuencia cardiaca",
        unit="ppm",
        sources={"garmin_details": "directHeartRate", "fit_record": "heart_rate"},
    ),
    MetricDefinition(
        key="speed",
        scope=_S,
        label="Velocidad",
        unit="m/s",
        sources={"garmin_details": "directSpeed", "fit_record": "enhanced_speed"},
    ),
    MetricDefinition(
        key="cadence",
        scope=_S,
        label="Cadencia",
        unit="ppm",
        sources={"garmin_details": "directRunCadence", "fit_record": "cadence"},
    ),
    MetricDefinition(
        key="altitude",
        scope=_S,
        label="Altitud",
        unit="m",
        sources={"garmin_details": "directElevation", "fit_record": "enhanced_altitude"},
    ),
    MetricDefinition(
        key="power",
        scope=_S,
        label="Potencia",
        unit="W",
        sources={"garmin_details": "directPower", "fit_record": "power"},
    ),
    MetricDefinition(
        key="lat",
        scope=_S,
        label="Latitud",
        unit="°",
        sources={"garmin_details": "directLatitude", "fit_record": "position_lat"},
    ),
    MetricDefinition(
        key="lon",
        scope=_S,
        label="Longitud",
        unit="°",
        sources={"garmin_details": "directLongitude", "fit_record": "position_long"},
    ),
    MetricDefinition(
        key="performance_condition",
        scope=_S,
        label="Condición de rendimiento",
        unit="",
        sources={"garmin_details": "directPerformanceCondition"},
    ),
    MetricDefinition(
        key="respiration_rate",
        scope=_S,
        label="Frecuencia respiratoria",
        unit="rpm",
        sources={"garmin_details": "directRespirationRate", "fit_record": "respiration_rate"},
    ),
    # ── Diarias ────────────────────────────────────────────────────────────
    MetricDefinition(
        key="resting_hr",
        scope=_D,
        label="FC en reposo",
        unit="ppm",
        higher_is_better=False,
        sources={"garmin_stats": "restingHeartRate"},
    ),
    MetricDefinition(
        key="hrv_last_night",
        scope=_D,
        label="HRV nocturna",
        unit="ms",
        higher_is_better=True,
        sources={"garmin_hrv": "hrvSummary.lastNightAvg"},
    ),
    MetricDefinition(
        key="sleep_seconds",
        scope=_D,
        label="Sueño",
        unit="s",
        higher_is_better=True,
        sources={"garmin_sleep": "dailySleepDTO.sleepTimeSeconds"},
    ),
    MetricDefinition(
        key="sleep_score",
        scope=_D,
        label="Puntuación de sueño",
        unit="",
        higher_is_better=True,
        sources={"garmin_sleep": "dailySleepDTO.sleepScores.overall.value"},
    ),
    MetricDefinition(
        key="body_battery_max",
        scope=_D,
        label="Body Battery máx.",
        unit="",
        higher_is_better=True,
        sources={"garmin_stats": "bodyBatteryHighestValue"},
    ),
    MetricDefinition(
        key="stress_avg",
        scope=_D,
        label="Estrés medio",
        unit="",
        higher_is_better=False,
        sources={"garmin_stats": "averageStressLevel"},
    ),
    MetricDefinition(
        key="steps_daily", scope=_D, label="Pasos diarios", unit="", sources={"garmin_stats": "totalSteps"}
    ),
    MetricDefinition(
        key="vo2max_running",
        scope=_D,
        label="VO2max carrera",
        unit="ml/kg/min",
        higher_is_better=True,
        sources={"garmin_max_metrics": "0.generic.vo2MaxPreciseValue"},
    ),
    MetricDefinition(
        key="vo2max_cycling",
        scope=_D,
        label="VO2max ciclismo",
        unit="ml/kg/min",
        higher_is_better=True,
        sources={"garmin_max_metrics": "0.cycling.vo2MaxPreciseValue"},
    ),
]


def seed_catalog(session: Session) -> int:
    """
    Inserta o actualiza (idempotente) el catálogo de métricas.

    Returns:
        Número de definiciones aplicadas.
    """
    for definition in CATALOG:
        session.merge(MetricDefinition.model_validate(definition.model_dump()))
    session.commit()
    return len(CATALOG)
