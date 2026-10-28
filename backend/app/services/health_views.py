"""
Vistas de salud de un día y de una noche (para la web y la IA), con la fuente que elige la persona.

- Noche: con Oura (si es la fuente de recuperación elegida o la única con datos) sale el detalle completo:
  fases, siestas, hipnograma, FC y HRV nocturnas, puntuación y contribuidores, preparación, hora óptima y
  SpO2. Con el reloj, el resumen que haya en las métricas diarias.
- Día: FC continua, actividad (puntuación, pasos, calorías, tiempos, clase cada 5 min, MET), estrés,
  resiliencia, sesiones, etiquetas y modo descanso.

Si el módulo `oura` está apagado para la cuenta, los datos de Oura no se enseñan (no se borran).
Solo se leen datos de la propia persona.
"""

from datetime import UTC, date, datetime, timedelta, timezone

from sqlmodel import Session, col, select

from app.models import DailyMetric, DailySeries, HealthTag, RestPeriod, User, WellnessSession
from app.services import daily_sources
from app.services.oura_sync import SOURCE as OURA
from app.services.oura_sync import main_and_naps, oura_enabled, parse_time


def oura_visible(session: Session, user: User) -> bool:
    return oura_enabled(session, user)


def _row(session: Session, user_id: int, day: date) -> DailyMetric | None:
    return session.exec(select(DailyMetric).where(DailyMetric.user_id == user_id, DailyMetric.day == day)).first()


def _series(session: Session, user_id: int, day: date, source: str) -> dict[str, dict]:
    rows = session.exec(select(DailySeries).where(
        DailySeries.user_id == user_id, DailySeries.day == day, DailySeries.source == source
    )).all()  # fmt: skip
    return {r.kind: r.data or {} for r in rows}


def _sample(data: dict | None) -> dict | None:
    if not data or not data.get("items"):
        return None
    return {"start": data.get("start"), "interval_s": data.get("interval"), "items": data["items"]}


def _period(p: dict) -> dict:
    return {
        "type": p.get("type"),
        "bedtime_start": p.get("bedtime_start"),
        "bedtime_end": p.get("bedtime_end"),
        "total_sleep_s": p.get("total_sleep_duration"),
        "deep_s": p.get("deep_sleep_duration"),
        "rem_s": p.get("rem_sleep_duration"),
        "light_s": p.get("light_sleep_duration"),
        "awake_s": p.get("awake_time"),
        "latency_s": p.get("latency"),
        "efficiency": p.get("efficiency"),
        "time_in_bed_s": p.get("time_in_bed"),
        "avg_hr": p.get("average_heart_rate"),
        "lowest_hr": p.get("lowest_heart_rate"),
        "avg_hrv": p.get("average_hrv"),
        "avg_breath": p.get("average_breath"),
        "restless_periods": p.get("restless_periods"),
    }


def _watch_period(metrics: dict) -> dict | None:
    """Resumen de la noche con lo que da el reloj (métricas diarias)."""
    if metrics.get("sleep_seconds") is None:
        return None
    m = metrics.get
    return {
        "type": "long_sleep", "bedtime_start": None, "bedtime_end": None, "total_sleep_s": m("sleep_seconds"),
        "deep_s": m("sleep_deep_s"), "rem_s": m("sleep_rem_s"), "light_s": m("sleep_light_s"),
        "awake_s": m("sleep_awake_s"), "latency_s": m("sleep_latency_s"), "efficiency": m("sleep_efficiency"),
        "time_in_bed_s": m("time_in_bed_s"), "avg_hr": m("avg_hr_sleep"), "lowest_hr": m("resting_hr"),
        "avg_hrv": m("hrv_last_night"), "avg_breath": m("breath_rate"), "restless_periods": m("restless_periods"),
    }  # fmt: skip


def _tags(session: Session, user_id: int, day: date, allow_oura: bool) -> list[dict]:
    query = select(HealthTag).where(HealthTag.user_id == user_id, HealthTag.day == day)
    if not allow_oura:
        query = query.where(HealthTag.source != OURA)
    rows = session.exec(query.order_by(col(HealthTag.start))).all()
    return [{"start": t.start, "end": t.end, "label": t.label, "comment": t.comment} for t in rows]


def night(session: Session, user: User, day: date) -> dict:
    """Detalle de la noche que termina el día `day` (contrato de `GET /health/night/{day}`)."""
    allow_oura = oura_visible(session, user)
    row = _row(session, user.id, day)
    oura = ((row.raw or {}).get(OURA) or {}) if row and allow_oura else {}
    has_oura = bool(oura.get("sleep") or oura.get("daily_sleep") or oura.get("daily_readiness"))
    stored = daily_sources.by_source(row) if row else {}
    watch = next((s for s in daily_sources.WATCH_SOURCES if stored.get(s, {}).get("sleep_seconds") is not None), None)
    prefer_oura = daily_sources.uses_oura(daily_sources.preferences(session, user.id))
    use_oura = has_oura and (prefer_oura or watch is None)
    out: dict = {
        "day": day, "source": None, "main": None, "naps": [], "hypnogram": None, "hr": None, "hrv": None,
        "sleep_score": None, "sleep_contributors": {}, "readiness": None, "sleep_time": None, "spo2": None,
        "tags": _tags(session, user.id, day, allow_oura),
    }  # fmt: skip
    if use_oura:
        main, naps = main_and_naps(oura.get("sleep") or [])
        series = _series(session, user.id, day, OURA)
        hyp = series.get("hypnogram_5min")
        daily_sleep = oura.get("daily_sleep") or {}
        readiness = oura.get("daily_readiness")
        sleep_time = oura.get("sleep_time")
        spo2 = oura.get("daily_spo2")
        out |= {
            "source": OURA,
            "main": _period(main) if main else None,
            "naps": [_period(p) for p in naps],
            "hypnogram": {"start": hyp.get("start"), "interval_s": 300, "phases": hyp.get("phases", "")}
            if hyp
            else None,
            "hr": _sample(series.get("sleep_hr")),
            "hrv": _sample(series.get("sleep_hrv")),
            "sleep_score": daily_sleep.get("score"),
            "sleep_contributors": daily_sleep.get("contributors") or {},
            "readiness": {
                "score": readiness.get("score"),
                "temperature_deviation": readiness.get("temperature_deviation"),
                "temperature_trend_deviation": readiness.get("temperature_trend_deviation"),
                "contributors": readiness.get("contributors") or {},
            }
            if readiness
            else None,
            "sleep_time": {k: sleep_time.get(k) for k in ("recommendation", "status", "optimal_bedtime")}
            if sleep_time
            else None,
            "spo2": {
                "average": (spo2.get("spo2_percentage") or {}).get("average"),
                "breathing_disturbance_index": spo2.get("breathing_disturbance_index"),
            }
            if spo2
            else None,
        }
    elif watch is not None:
        values = stored[watch]
        out |= {"source": watch, "main": _watch_period(values), "sleep_score": values.get("sleep_score")}
    return out


def _day_window(oura: dict, day: date) -> tuple[datetime, datetime]:
    """Día local (con la zona horaria que dan los documentos de Oura de ese día; si no, UTC)."""
    for ts in ((oura.get("daily_activity") or {}).get("timestamp"),
               *(p.get("bedtime_end") for p in oura.get("sleep") or [])):  # fmt: skip
        t = parse_time(ts)
        if t is not None and t.utcoffset() is not None:
            tz = timezone(t.utcoffset())
            start = datetime(day.year, day.month, day.day, tzinfo=tz)
            return start, start + timedelta(days=1)
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


def active_rest_period(session: Session, user_id: int, day: date | None = None) -> RestPeriod | None:
    """Modo descanso activo ese día (o hoy)."""
    day = day or date.today()
    return session.exec(
        select(RestPeriod)
        .where(RestPeriod.user_id == user_id, RestPeriod.start_date <= day)
        .where((col(RestPeriod.end_date).is_(None)) | (col(RestPeriod.end_date) >= day))
        .order_by(col(RestPeriod.start_date).desc())
    ).first()


def day_view(session: Session, user: User, day: date) -> dict:
    """Detalle de un día (contrato de `GET /health/day/{day}`)."""
    allow_oura = oura_visible(session, user)
    row = _row(session, user.id, day)
    oura = ((row.raw or {}).get(OURA) or {}) if row and allow_oura else {}
    t0, t1 = _day_window(oura, day)
    sources_query = select(DailySeries).where(
        DailySeries.user_id == user.id, DailySeries.kind == "heartrate",
        col(DailySeries.day).in_([day - timedelta(days=1), day, day + timedelta(days=1)]),
    )  # fmt: skip
    if not allow_oura:
        sources_query = sources_query.where(DailySeries.source != OURA)
    points = sorted(
        {
            int(p[0]): p
            for r in session.exec(sources_query).all()
            for p in (r.data or {}).get("points") or []
            if t0.timestamp() <= p[0] < t1.timestamp()
        }.values()  # fmt: skip
    )
    series = _series(session, user.id, day, OURA) if allow_oura else {}
    act = oura.get("daily_activity")
    activity = None
    if act:
        classes, met = series.get("activity_class_5min"), series.get("met")
        activity = {
            "score": act.get("score"), "steps": act.get("steps"), "active_calories": act.get("active_calories"),
            "total_calories": act.get("total_calories"), "high_s": act.get("high_activity_time"),
            "medium_s": act.get("medium_activity_time"), "low_s": act.get("low_activity_time"),
            "sedentary_s": act.get("sedentary_time"), "non_wear_s": act.get("non_wear_time"),
            "class_5min": {"start": classes.get("start"), "classes": classes.get("classes", "")} if classes else None,
            "met": _sample(met),
        }  # fmt: skip
    stress, resilience = oura.get("daily_stress"), oura.get("daily_resilience")
    sessions_query = select(WellnessSession).where(
        WellnessSession.user_id == user.id,
        col(WellnessSession.start) >= t0 - timedelta(hours=12),
        col(WellnessSession.start) < t1 + timedelta(hours=12),
    )
    if not allow_oura:
        sessions_query = sessions_query.where(WellnessSession.source != OURA)
    sessions = [
        s for s in session.exec(sessions_query.order_by(col(WellnessSession.start))).all()
        if (s.raw or {}).get("day") == day.isoformat() or (not (s.raw or {}).get("day") and t0 <= s.start < t1)
    ]  # fmt: skip
    rest = active_rest_period(session, user.id, day)
    if rest is not None and rest.source == OURA and not allow_oura:
        rest = None
    return {
        "day": day,
        "heartrate": points,
        "activity": activity,
        "stress": {
            "stress_high_s": stress.get("stress_high"),
            "recovery_high_s": stress.get("recovery_high"),
            "day_summary": stress.get("day_summary"),
        }
        if stress
        else None,  # fmt: skip
        "resilience": {"level": resilience.get("level"), "contributors": resilience.get("contributors") or {}}
        if resilience
        else None,
        "sessions": [
            {"type": s.type, "start": s.start, "end": s.end, "mood": s.mood, "hr_avg": s.hr_avg, "hrv_avg": s.hrv_avg}
            for s in sessions
        ],  # fmt: skip
        "tags": _tags(session, user.id, day, allow_oura),
        "rest_mode": {"start_date": rest.start_date, "end_date": rest.end_date} if rest else None,
    }


def rest_periods(session: Session, user: User, date_from: date, date_to: date) -> list[dict]:
    """Periodos de modo descanso que se solapan con el rango."""
    query = (
        select(RestPeriod)
        .where(RestPeriod.user_id == user.id, RestPeriod.start_date <= date_to)
        .where((col(RestPeriod.end_date).is_(None)) | (col(RestPeriod.end_date) >= date_from))
    )
    if not oura_visible(session, user):
        query = query.where(RestPeriod.source != OURA)
    rows = session.exec(query.order_by(col(RestPeriod.start_date))).all()
    return [{"start_date": r.start_date, "end_date": r.end_date, "source": r.source} for r in rows]
