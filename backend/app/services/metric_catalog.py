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
        key="max_power",
        scope=_A,
        label="Potencia máxima",
        unit="W",
        higher_is_better=True,
        sources={"garmin_summary": "maxPower", "fit_session": "max_power"},
    ),
    MetricDefinition(
        key="max_20min_power",
        scope=_A,
        label="Mejor potencia en 20 min",
        unit="W",
        higher_is_better=True,
        sources={"garmin_summary": "max20MinPower"},
    ),
    MetricDefinition(
        key="max_cadence",
        scope=_A,
        label="Cadencia máxima",
        unit="ppm",
        sources={"garmin_summary": "maxRunningCadenceInStepsPerMinute|maxBikingCadenceInRevPerMinute"},
    ),
    MetricDefinition(
        key="avg_vertical_oscillation",
        scope=_A,
        label="Oscilación vertical",
        unit="cm",
        higher_is_better=False,
        sources={"garmin_summary": "avgVerticalOscillation", "fit_session": "avg_vertical_oscillation"},
    ),
    MetricDefinition(
        key="avg_ground_contact_time",
        scope=_A,
        label="Tiempo de contacto con el suelo",
        unit="ms",
        higher_is_better=False,
        sources={"garmin_summary": "avgGroundContactTime", "fit_session": "avg_stance_time"},
    ),
    MetricDefinition(
        key="avg_vertical_ratio",
        scope=_A,
        label="Ratio vertical",
        unit="%",
        higher_is_better=False,
        sources={"garmin_summary": "avgVerticalRatio", "fit_session": "avg_vertical_ratio"},
    ),
    MetricDefinition(
        key="avg_gct_balance",
        scope=_A,
        label="Equilibrio del contacto (izq.)",
        unit="%",
        sources={"garmin_summary": "avgGroundContactBalance"},
    ),
    MetricDefinition(
        key="grade_adjusted_speed",
        scope=_A,
        label="Velocidad ajustada a pendiente",
        unit="m/s",
        higher_is_better=True,
        sources={"garmin_summary": "avgGradeAdjustedSpeed"},
    ),
    MetricDefinition(
        key="avg_respiration",
        scope=_A,
        label="Respiración media",
        unit="rpm",
        sources={"garmin_summary": "avgRespirationRate"},
    ),
    MetricDefinition(
        key="max_respiration",
        scope=_A,
        label="Respiración máxima",
        unit="rpm",
        sources={"garmin_summary": "maxRespirationRate"},
    ),
    MetricDefinition(
        key="min_temperature",
        scope=_A,
        label="Temperatura mínima",
        unit="°C",
        sources={"garmin_summary": "minTemperature", "fit_session": "min_temperature"},
    ),
    MetricDefinition(
        key="max_temperature",
        scope=_A,
        label="Temperatura máxima",
        unit="°C",
        sources={"garmin_summary": "maxTemperature", "fit_session": "max_temperature"},
    ),
    MetricDefinition(
        key="sweat_loss_ml",
        scope=_A,
        label="Pérdida de sudor estimada",
        unit="ml",
        sources={"garmin_summary": "waterEstimated"},
    ),
    MetricDefinition(
        key="body_battery_delta",
        scope=_A,
        label="Body Battery consumido",
        unit="",
        sources={"garmin_summary": "differenceBodyBattery"},
    ),
    MetricDefinition(
        key="session_intensity_min_moderate",
        scope=_A,
        label="Minutos de intensidad moderada",
        unit="min",
        sources={"garmin_summary": "moderateIntensityMinutes"},
    ),
    MetricDefinition(
        key="session_intensity_min_vigorous",
        scope=_A,
        label="Minutos de intensidad vigorosa",
        unit="min",
        sources={"garmin_summary": "vigorousIntensityMinutes"},
    ),
    MetricDefinition(
        key="avg_swolf",
        scope=_A,
        label="SWOLF medio",
        unit="",
        higher_is_better=False,
        sources={"garmin_summary": "averageSwolf"},
    ),
    MetricDefinition(key="total_strokes", scope=_A, label="Brazadas", unit="", sources={"garmin_summary": "strokes"}),
    MetricDefinition(
        key="avg_stroke_rate",
        scope=_A,
        label="Ritmo de brazada",
        unit="brazadas/min",
        sources={"garmin_summary": "averageSwimCadenceInStrokesPerMinute"},
    ),
    MetricDefinition(
        key="pool_length", scope=_A, label="Largo de piscina", unit="m", sources={"garmin_summary": "poolLength"}
    ),
    MetricDefinition(
        key="active_lengths", scope=_A, label="Largos", unit="", sources={"garmin_summary": "activeLengths"}
    ),
    MetricDefinition(
        key="avg_left_balance",
        scope=_A,
        label="Equilibrio de pedaleo (izq.)",
        unit="%",
        sources={"garmin_summary": "avgLeftBalance"},
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


def _daily(key: str, label: str, unit: str = "", better: bool | None = None,
           garmin: dict[str, str] | None = None) -> MetricDefinition:  # fmt: skip
    """
    Métrica diaria. `garmin` = rutas en la respuesta diaria de Garmin (`{"garmin_stats": "campo"}`); sin
    ella la rellenan otras fuentes (Oura, Apple…). Si el reloj no da el dato, simplemente no aparece.
    """
    return MetricDefinition(key=key, scope=_D, label=label, unit=unit, higher_is_better=better, sources=garmin or {})


# ── Diarias de Oura (y de cualquier fuente que las dé) ─────────────────────
OURA_DAILY: list[MetricDefinition] = [
    _daily("readiness_score", "Preparación (readiness)", "", True),
    _daily("temperature_deviation", "Desviación de temperatura", "°C"),
    _daily("temperature_trend_deviation", "Tendencia de temperatura", "°C"),
    _daily("active_calories", "Calorías activas", "kcal", garmin={"garmin_stats": "activeKilocalories"}),
    _daily("total_calories", "Calorías totales", "kcal", garmin={"garmin_stats": "totalKilocalories"}),
    _daily("spo2_avg", "SpO2 media", "%", True, garmin={"garmin_stats": "averageSpo2"}),
    _daily("breathing_disturbance_index", "Índice de alteraciones respiratorias", "", False),
    _daily("stress_high_s", "Tiempo con estrés alto", "s", False, garmin={"garmin_stats": "highStressDuration"}),
    _daily("recovery_high_s", "Tiempo en recuperación alta", "s", True),
    _daily("resilience_level", "Resiliencia (1 limitada – 5 excepcional)", "", True),
    _daily("vo2max_oura", "VO2max (Oura)", "ml/kg/min", True),
    _daily("cardio_age", "Edad cardiovascular", "años", False),
    _daily("pulse_wave_velocity", "Velocidad de onda de pulso", "m/s", False),
    _daily("sleep_deep_s", "Sueño profundo", "s", True, garmin={"garmin_sleep": "dailySleepDTO.deepSleepSeconds"}),
    _daily("sleep_rem_s", "Sueño REM", "s", True, garmin={"garmin_sleep": "dailySleepDTO.remSleepSeconds"}),
    _daily("sleep_light_s", "Sueño ligero", "s", garmin={"garmin_sleep": "dailySleepDTO.lightSleepSeconds"}),
    _daily(
        "sleep_awake_s", "Despierto en la cama", "s", False, garmin={"garmin_sleep": "dailySleepDTO.awakeSleepSeconds"}
    ),
    _daily("sleep_latency_s", "Tiempo en dormirse", "s", False),
    _daily("sleep_efficiency", "Eficiencia del sueño", "%", True),
    _daily("time_in_bed_s", "Tiempo en la cama", "s"),
    _daily("restless_periods", "Periodos inquietos", "", False),
    _daily(
        "breath_rate", "Respiración nocturna", "rpm", garmin={"garmin_sleep": "dailySleepDTO.averageRespirationValue"}
    ),
    _daily("avg_hr_sleep", "FC media durmiendo", "ppm", False, garmin={"garmin_sleep": "dailySleepDTO.avgHeartRate"}),
    _daily("naps_s", "Siestas", "s"),
    _daily("activity_score", "Puntuación de actividad", "", True),
    _daily("high_activity_time_s", "Actividad alta", "s", garmin={"garmin_stats": "highlyActiveSeconds"}),
    _daily("medium_activity_time_s", "Actividad media", "s"),
    _daily("low_activity_time_s", "Actividad baja", "s"),
    _daily("sedentary_time_s", "Tiempo sedentario", "s", False, garmin={"garmin_stats": "sedentarySeconds"}),
    _daily("high_activity_met_min", "MET-min de actividad alta", "MET-min"),
    _daily("medium_activity_met_min", "MET-min de actividad media", "MET-min"),
    _daily("low_activity_met_min", "MET-min de actividad baja", "MET-min"),
    _daily("sedentary_met_min", "MET-min sedentarios", "MET-min"),
    _daily("non_wear_s", "Tiempo sin el anillo", "s"),
    _daily("inactivity_alerts", "Avisos de inactividad", "", False),
    _daily("equivalent_walking_distance", "Distancia equivalente andando", "m"),
]
# ── Diarias que dan los relojes (Garmin) además de las de arriba ───────────
WATCH_DAILY: list[MetricDefinition] = [
    _daily("stress_max", "Estrés máximo", "", False, garmin={"garmin_stats": "maxStressLevel"}),
    _daily("stress_rest_s", "Tiempo en descanso (estrés)", "s", True, garmin={"garmin_stats": "restStressDuration"}),
    _daily("stress_low_s", "Tiempo con estrés bajo", "s", garmin={"garmin_stats": "lowStressDuration"}),
    _daily("stress_medium_s", "Tiempo con estrés medio", "s", False, garmin={"garmin_stats": "mediumStressDuration"}),
    _daily(
        "sleep_stress_avg",
        "Estrés durante el sueño",
        "",
        False,
        garmin={"garmin_sleep": "dailySleepDTO.avgSleepStress"},
    ),
    _daily("body_battery_min", "Body Battery mín.", "", True, garmin={"garmin_stats": "bodyBatteryLowestValue"}),
    _daily(
        "body_battery_wake", "Body Battery al despertar", "", True, garmin={"garmin_stats": "bodyBatteryAtWakeTime"}
    ),
    _daily(
        "body_battery_charged", "Body Battery cargado", "", True, garmin={"garmin_stats": "bodyBatteryChargedValue"}
    ),
    _daily("body_battery_drained", "Body Battery gastado", "", garmin={"garmin_stats": "bodyBatteryDrainedValue"}),
    _daily("spo2_lowest", "SpO2 mínima", "%", True, garmin={"garmin_stats": "lowestSpo2"}),
    _daily("max_hr_daily", "FC máxima del día", "ppm", garmin={"garmin_stats": "maxHeartRate"}),
    _daily(
        "intensity_min_moderate",
        "Minutos de intensidad moderada",
        "min",
        garmin={"garmin_stats": "moderateIntensityMinutes"},
    ),
    _daily(
        "intensity_min_vigorous",
        "Minutos de intensidad vigorosa",
        "min",
        garmin={"garmin_stats": "vigorousIntensityMinutes"},
    ),
    _daily("floors_ascended", "Pisos subidos", "", garmin={"garmin_stats": "floorsAscended"}),
    _daily("hrv_weekly_avg", "HRV media de 7 días", "ms", True, garmin={"garmin_hrv": "hrvSummary.weeklyAvg"}),
    _daily(
        "training_readiness", "Preparación para entrenar", "", True, garmin={"garmin_training_readiness": "0.score"}
    ),
]
CATALOG += WATCH_DAILY
# ── De una sesión: las que dan el anillo Oura (y cualquier fuente que las tenga) ──
SESSION_EXTRA: list[MetricDefinition] = [
    MetricDefinition(key="min_hr", scope=_A, label="FC mínima", unit="ppm"),
    MetricDefinition(key="avg_met", scope=_A, label="MET medio", unit="MET"),
    MetricDefinition(key="max_met", scope=_A, label="MET máximo", unit="MET"),
    # 1 suave · 2 moderada · 3 alta (la intensidad que asigna Oura al entreno).
    MetricDefinition(key="oura_intensity", scope=_A, label="Intensidad según Oura", unit=""),
    # 1 a mano · 2 detectado solo · 3 detectado y confirmado · 4 con FC de entreno.
    MetricDefinition(key="oura_origin", scope=_A, label="Registro en Oura", unit=""),
    MetricDefinition(key="met", scope=_S, label="Intensidad (MET)", unit="MET"),
]
CATALOG += SESSION_EXTRA
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
