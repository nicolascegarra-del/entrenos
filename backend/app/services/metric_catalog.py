"""
Catálogo inicial de métricas, basado en lo que devuelve un Forerunner 735XT
más las que traen relojes más recientes (potencia, HRV...). Añadir una métrica
nueva es añadir una entrada aquí y ejecutar `python -m app.cli seed-catalog`.
"""

from sqlmodel import Session

from app.models import MetricDefinition, MetricScope

RUN, BIKE, STRENGTH = "running", "cycling", "strength_training"

# Distancia (m) de cada récord, para la vista de mejores marcas.
RECORD_DISTANCES = {
    "best_1k": 1000,
    "best_mile": 1609,
    "best_5k": 5000,
    "best_10k": 10000,
    "best_half": 21098,
    "best_marathon": 42195,
}

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
        sources={"garmin_summary": "averageRunningCadenceInStepsPerMinute|averageBikingCadenceInRevPerMinute"},
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
    MetricDefinition(key="steps", scope=_A, label="Pasos", unit="", sports=[RUN], sources={"garmin_summary": "steps"}),
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
    # Mejores tiempos dentro de la actividad (Garmin los calcula: fastestSplit_<metros>).
    MetricDefinition(
        key="best_1k",
        scope=_A,
        label="Mejor 1 km",
        unit="s",
        higher_is_better=False,
        sports=[RUN],
        sources={"garmin_summary": "fastestSplit_1000"},
    ),
    MetricDefinition(
        key="best_mile",
        scope=_A,
        label="Mejor milla",
        unit="s",
        higher_is_better=False,
        sports=[RUN],
        sources={"garmin_summary": "fastestSplit_1609"},
    ),
    MetricDefinition(
        key="best_5k",
        scope=_A,
        label="Mejor 5 km",
        unit="s",
        higher_is_better=False,
        sports=[RUN],
        sources={"garmin_summary": "fastestSplit_5000"},
    ),
    MetricDefinition(
        key="best_10k",
        scope=_A,
        label="Mejor 10 km",
        unit="s",
        higher_is_better=False,
        sports=[RUN],
        sources={"garmin_summary": "fastestSplit_10000"},
    ),
    MetricDefinition(
        key="best_half",
        scope=_A,
        label="Mejor media maratón",
        unit="s",
        higher_is_better=False,
        sports=[RUN],
        sources={"garmin_summary": "fastestSplit_21098"},
    ),
    MetricDefinition(
        key="best_marathon",
        scope=_A,
        label="Mejor maratón",
        unit="s",
        higher_is_better=False,
        sports=[RUN],
        sources={"garmin_summary": "fastestSplit_42195"},
    ),
    MetricDefinition(
        key="vo2max",
        scope=_A,
        label="VO2max estimado",
        unit="ml/kg/min",
        higher_is_better=True,
        sports=[RUN, BIKE],
        sources={"garmin_summary": "vO2MaxValue"},
    ),
    MetricDefinition(
        key="lthr",
        scope=_A,
        label="FC umbral láctico",
        unit="ppm",
        sources={"garmin_summary": "lactateThresholdBpm"},
    ),
    # Tiempo en cada zona de FC de Garmin (Z1 50–60 % … Z5 90–100 % de la FC máx.).
    MetricDefinition(
        key="hr_zone_1_s",
        scope=_A,
        label="Tiempo en Z1",
        unit="s",
        sources={"garmin_summary": "hrTimeInZone_1"},
    ),
    MetricDefinition(
        key="hr_zone_2_s",
        scope=_A,
        label="Tiempo en Z2",
        unit="s",
        sources={"garmin_summary": "hrTimeInZone_2"},
    ),
    MetricDefinition(
        key="hr_zone_3_s",
        scope=_A,
        label="Tiempo en Z3",
        unit="s",
        sources={"garmin_summary": "hrTimeInZone_3"},
    ),
    MetricDefinition(
        key="hr_zone_4_s",
        scope=_A,
        label="Tiempo en Z4",
        unit="s",
        sources={"garmin_summary": "hrTimeInZone_4"},
    ),
    MetricDefinition(
        key="hr_zone_5_s",
        scope=_A,
        label="Tiempo en Z5",
        unit="s",
        sources={"garmin_summary": "hrTimeInZone_5"},
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
        # Carrera: pasos/min totales (directDoubleCadence); bici: rpm.
        sources={"garmin_details": "directDoubleCadence|directBikeCadence|directRunCadence", "fit_record": "cadence"},
    ),
    MetricDefinition(
        key="altitude",
        scope=_S,
        label="Altitud",
        unit="m",
        sources={"garmin_details": "directElevation", "fit_record": "enhanced_altitude"},
    ),
    MetricDefinition(
        key="distance",
        scope=_S,
        label="Distancia",
        unit="m",
        sources={"garmin_details": "sumDistance", "fit_record": "distance"},
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


def _daily(key: str, label: str, unit: str = "", better: bool | None = None) -> MetricDefinition:
    """Métrica diaria sin ruta de Garmin (la rellenan otras fuentes, p. ej. el anillo Oura)."""
    return MetricDefinition(key=key, scope=_D, label=label, unit=unit, higher_is_better=better, sources={})


# ── Diarias de Oura (y de cualquier fuente que las dé) ─────────────────────
OURA_DAILY: list[MetricDefinition] = [
    _daily("readiness_score", "Preparación (readiness)", "", True),
    _daily("temperature_deviation", "Desviación de temperatura", "°C"),
    _daily("temperature_trend_deviation", "Tendencia de temperatura", "°C"),
    _daily("active_calories", "Calorías activas", "kcal"),
    _daily("total_calories", "Calorías totales", "kcal"),
    _daily("spo2_avg", "SpO2 media nocturna", "%", True),
    _daily("breathing_disturbance_index", "Índice de alteraciones respiratorias", "", False),
    _daily("stress_high_s", "Tiempo con estrés alto", "s", False),
    _daily("recovery_high_s", "Tiempo en recuperación alta", "s", True),
    _daily("resilience_level", "Resiliencia (1 limitada – 5 excepcional)", "", True),
    _daily("vo2max_oura", "VO2max (Oura)", "ml/kg/min", True),
    _daily("cardio_age", "Edad cardiovascular", "años", False),
    _daily("pulse_wave_velocity", "Velocidad de onda de pulso", "m/s", False),
    _daily("sleep_deep_s", "Sueño profundo", "s", True),
    _daily("sleep_rem_s", "Sueño REM", "s", True),
    _daily("sleep_light_s", "Sueño ligero", "s"),
    _daily("sleep_awake_s", "Despierto en la cama", "s", False),
    _daily("sleep_latency_s", "Tiempo en dormirse", "s", False),
    _daily("sleep_efficiency", "Eficiencia del sueño", "%", True),
    _daily("time_in_bed_s", "Tiempo en la cama", "s"),
    _daily("restless_periods", "Periodos inquietos", "", False),
    _daily("breath_rate", "Respiración nocturna", "rpm"),
    _daily("avg_hr_sleep", "FC media durmiendo", "ppm", False),
    _daily("naps_s", "Siestas", "s"),
    _daily("activity_score", "Puntuación de actividad", "", True),
    _daily("high_activity_time_s", "Actividad alta", "s"),
    _daily("medium_activity_time_s", "Actividad media", "s"),
    _daily("low_activity_time_s", "Actividad baja", "s"),
    _daily("sedentary_time_s", "Tiempo sedentario", "s", False),
    _daily("high_activity_met_min", "MET-min de actividad alta", "MET-min"),
    _daily("medium_activity_met_min", "MET-min de actividad media", "MET-min"),
    _daily("low_activity_met_min", "MET-min de actividad baja", "MET-min"),
    _daily("sedentary_met_min", "MET-min sedentarios", "MET-min"),
    _daily("non_wear_s", "Tiempo sin el anillo", "s"),
    _daily("inactivity_alerts", "Avisos de inactividad", "", False),
    _daily("equivalent_walking_distance", "Distancia equivalente andando", "m"),
]
# Contribuidores (0–100) de cada puntuación de Oura.
OURA_CONTRIBUTORS: dict[str, dict[str, str]] = {
    "readiness": {
        "activity_balance": "equilibrio de actividad", "body_temperature": "temperatura corporal",
        "hrv_balance": "equilibrio de HRV", "previous_day_activity": "actividad del día anterior",
        "previous_night": "noche anterior", "recovery_index": "índice de recuperación",
        "resting_heart_rate": "FC en reposo", "sleep_balance": "equilibrio de sueño",
        "sleep_regularity": "regularidad del sueño",
    },
    "sleep": {
        "deep_sleep": "sueño profundo", "efficiency": "eficiencia", "latency": "latencia", "rem_sleep": "sueño REM",
        "restfulness": "descanso", "timing": "horario", "total_sleep": "sueño total",
    },
    "activity": {
        "meet_daily_targets": "objetivos diarios", "move_every_hour": "moverse cada hora",
        "recovery_time": "tiempo de recuperación", "stay_active": "mantenerse activo",
        "training_frequency": "frecuencia de entreno", "training_volume": "volumen de entreno",
    },
    "resilience": {"sleep_recovery": "recuperación nocturna", "daytime_recovery": "recuperación diurna",
                   "stress": "estrés"},
}  # fmt: skip
_SCORE_LABEL = {"readiness": "Preparación", "sleep": "Sueño", "activity": "Actividad", "resilience": "Resiliencia"}
OURA_DAILY += [
    _daily(f"oura_{group}_{key}", f"{_SCORE_LABEL[group]} · {label}", "", True)
    for group, items in OURA_CONTRIBUTORS.items()
    for key, label in items.items()
]
CATALOG += OURA_DAILY


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
