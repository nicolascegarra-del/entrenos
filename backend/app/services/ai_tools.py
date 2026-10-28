"""
Herramientas de consulta para el asistente de IA (function calling).

El modelo las llama cuando necesita datos concretos: actividades de cualquier fecha con vueltas, parciales,
tiempo en zonas y series de FC/ritmo; zonas y umbrales; progresión; marcas; plan y objetivos; salud diaria;
lesiones y material. Todas son de solo lectura, filtran por el usuario y devuelven JSON compacto en
español (unidades en el nombre del campo). Nunca se envían coordenadas GPS, email ni nombre.
"""

import json
import logging
from collections.abc import Callable
from datetime import date, timedelta

from sqlmodel import Session, col, select

from app.models import Activity, ActivityFeedback, ActivityStream, DailyMetric, Gear, Lap, PlannedSession, RaceGoal
from app.services import coach
from app.services import progress as prog
from app.services.insights import decoupling_pct, is_steady
from app.services.llm import ToolSpec
from app.services.metric_catalog import CATALOG, RECORD_DISTANCES
from app.services.plan_steps import local_day, sport_family
from app.services.streams import downsample

logger = logging.getLogger(__name__)

MAX_RESULT_CHARS = 12_000
MAX_SERIES_POINTS = 300
SERIES_CHANNELS = {"fc": "hr", "velocidad": "speed", "altitud": "altitude", "cadencia": "cadence", "potencia": "power"}
LABELS = {d.key: (d.label, d.unit) for d in CATALOG}
DAILY_KEYS = (
    "resting_hr",
    "hrv_last_night",
    "sleep_seconds",
    "sleep_score",
    "body_battery_max",
    "stress_avg",
    "steps_daily",
    "lt_speed",
    "lt_hr",
)


class ToolError(ValueError):
    """Petición de la IA que no se puede atender (id ajeno, fechas mal…): se le devuelve el motivo."""


# ─── Formato ─────────────────────────────────────────────────────────────────


def clock(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    s = round(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def pace(seconds_per_km: float | None) -> str | None:
    return f"{clock(seconds_per_km)}/km" if seconds_per_km else None


def _pace_of(distance_m: float | None, seconds: float | None) -> str | None:
    if not distance_m or distance_m < 100 or not seconds:
        return None
    return pace(seconds / distance_m * 1000)


def _speed_pace(speed: float | None) -> str | None:
    return pace(1000 / speed) if speed and speed > 0.5 else None


def _r(value: float | None, digits: int = 1) -> float | None:
    return round(value, digits) if isinstance(value, int | float) else None


def _clean(d: dict) -> dict:
    """Quita claves vacías para ahorrar tokens."""
    return {k: v for k, v in d.items() if v not in (None, "", [], {})}


def _day(value: str | None, default: date) -> date:
    if not value:
        return default
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise ToolError(f"Fecha no válida: {value!r}. Usa el formato AAAA-MM-DD.") from exc


def _ddmm(d: date) -> str:
    return d.strftime("%d/%m/%Y")


# ─── Datos comunes ───────────────────────────────────────────────────────────


def _owned_activity(session: Session, user_id: int, activity_id) -> Activity:
    try:
        aid = int(activity_id)
    except (TypeError, ValueError) as exc:
        raise ToolError("El id de actividad debe ser un número.") from exc
    a = session.get(Activity, aid)
    if a is None or a.user_id != user_id:
        raise ToolError(f"No existe ninguna actividad tuya con id {aid}. Búscala con buscar_actividades.")
    return a


def _channels(session: Session, activity_id: int, names: list[str]) -> dict[str, list]:
    rows = session.exec(
        select(ActivityStream).where(ActivityStream.activity_id == activity_id, col(ActivityStream.channel).in_(names))
    ).all()
    return {r.channel: r.values for r in rows}


def _activity_row(a: Activity, loads: dict[int, float], compliance: dict[int, float]) -> dict:
    m = a.metrics or {}
    return _clean(
        {
            "id": a.id,
            "fecha": local_day(a.start_time, a.timezone).isoformat(),
            "deporte": a.sport,
            "nombre": a.name,
            "km": _r((a.distance_m or 0) / 1000, 2) if a.distance_m else None,
            "tiempo": clock(a.duration_s),
            "tiempo_mov": clock(a.moving_duration_s) if a.moving_duration_s else None,
            "ritmo": _pace_of(a.distance_m, a.moving_duration_s or a.duration_s)
            if sport_family(a.sport) == "running"
            else None,
            "fc_media": _r(a.avg_hr, 0),
            "fc_max": _r(a.max_hr, 0),
            "desnivel_m": _r(a.elevation_gain_m, 0),
            "carga": _r(loads.get(a.id), 0),
            "te_aerobico": _r(m.get("aerobic_te")),
            "te_anaerobico": _r(m.get("anaerobic_te")),
            "carrera_a_tope": a.is_race or None,
            "cumplimiento_plan_pct": _r(compliance.get(a.id), 0),
        }
    )


def _compliance_by_activity(session: Session, user_id: int) -> dict[int, float]:
    rows = session.exec(
        select(PlannedSession.activity_id, PlannedSession.compliance_score).where(
            PlannedSession.user_id == user_id,
            col(PlannedSession.activity_id).is_not(None),
            col(PlannedSession.compliance_score).is_not(None),
        )
    ).all()
    return dict(rows)


# ─── Herramientas ────────────────────────────────────────────────────────────


def buscar_actividades(session: Session, user_id: int, args: dict) -> tuple[str, dict]:
    today = date.today()
    hasta = _day(args.get("hasta"), today)
    desde = _day(args.get("desde"), hasta - timedelta(days=30))
    if desde > hasta:
        desde, hasta = hasta, desde
    limit = max(1, min(int(args.get("limite") or 30), 50))
    sport = (args.get("deporte") or "").strip().lower()
    text = (args.get("texto") or "").strip().lower()
    activities = prog.user_activities(session, user_id)
    _, loads = prog.loads_by_day(activities, prog.user_thresholds(session, user_id), prog.user_rpes(session, user_id))
    compliance = _compliance_by_activity(session, user_id)
    found = [
        a
        for a in activities
        if desde <= local_day(a.start_time, a.timezone) <= hasta
        and (not sport or sport in (a.sport, sport_family(a.sport)))
        and (not text or text in (a.name or "").lower())
        and (not args.get("solo_carreras") or a.is_race)
    ]
    rows = [_activity_row(a, loads, compliance) for a in reversed(found)][:limit]
    label = f"Actividades del {_ddmm(desde)} al {_ddmm(hasta)}"
    return label, {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "total_en_el_periodo": len(found),
        "mostradas": len(rows),
        "actividades": rows,
    }


def _time_in_zones(time: list, hr: list, zones: list[dict]) -> list[dict]:
    """Minutos en cada zona de FC de la app a partir de la serie de pulso."""
    if not zones or not time or not hr:
        return []
    secs = [0.0] * len(zones)
    for i in range(1, min(len(time), len(hr))):
        h, t0, t1 = hr[i], time[i - 1], time[i]
        if h is None or t0 is None or t1 is None or t1 <= t0 or t1 - t0 > 30:
            continue
        idx = next((k for k, z in enumerate(zones) if z["max"] is None or h <= z["max"]), len(zones) - 1)
        secs[idx] += t1 - t0
    return [{"zona": z["name"], "min": round(s / 60, 1)} for z, s in zip(zones, secs, strict=False)]


def detalle_actividad(session: Session, user_id: int, args: dict) -> tuple[str, dict]:
    from app.services.routes import _series, _splits
    from app.services.zones import latest_zones

    a = _owned_activity(session, user_id, args.get("id"))
    day = local_day(a.start_time, a.timezone)
    activities = prog.user_activities(session, user_id)
    _, loads = prog.loads_by_day(activities, prog.user_thresholds(session, user_id), prog.user_rpes(session, user_id))
    out = _activity_row(a, loads, _compliance_by_activity(session, user_id))
    metrics = {}
    for key, value in (a.metrics or {}).items():
        if not isinstance(value, int | float) or isinstance(value, bool) or key not in LABELS:
            continue
        label, unit = LABELS[key]
        if key in RECORD_DISTANCES:
            metrics[label] = clock(value)
        elif key.startswith("hr_zone_"):
            metrics[f"{label} (min)"] = round(value / 60, 1)
        else:
            metrics[f"{label}{f' ({unit})' if unit else ''}"] = _r(value, 2)
    out["metricas_del_reloj"] = metrics
    laps = session.exec(select(Lap).where(Lap.activity_id == a.id).order_by(Lap.index)).all()
    out["vueltas"] = [
        _clean(
            {
                "n": lap.index + 1,
                "km": _r((lap.distance_m or 0) / 1000, 2),
                "tiempo": clock(lap.duration_s),
                "ritmo": _speed_pace(lap.avg_speed),
                "fc_media": _r(lap.avg_hr, 0),
                "fc_max": _r(lap.max_hr, 0),
                "cadencia": _r((lap.metrics or {}).get("avg_cadence"), 0),
            }
        )
        for lap in laps[:60]
    ]
    ch = _channels(session, a.id, ["time", "distance", "hr", "speed", "altitude"])
    if ch.get("distance") and ch.get("time"):
        d, s = _series(ch)
        if d:
            out["parciales_km"] = [
                _clean({"km": k + 1, "tiempo": clock(t)})
                for k, t in enumerate(_splits(d, s.get("time", []), d[-1])[:60])
            ]
    zones = latest_zones(session, user_id)
    if zones and ch.get("hr"):
        out["tiempo_en_zonas_fc_app"] = _time_in_zones(ch.get("time", []), ch["hr"], zones.zones.get("hr") or [])
    if ch.get("hr") and ch.get("speed"):
        dec = decoupling_pct(ch)
        if dec is not None:
            out["desacople_fc_ritmo_pct"] = dec
            out["ritmo_constante"] = is_steady(ch)
    fb = session.get(ActivityFeedback, a.id)
    if fb:
        out["sensaciones"] = _clean({"rpe_1a10": fb.rpe, "como_te_sentiste_1a5": fb.feeling, "notas": fb.notes})
    planned = session.exec(select(PlannedSession).where(PlannedSession.activity_id == a.id)).first()
    if planned:
        steps = [
            _clean({"paso": i + 1, "estado": st.get("status"), "nota": _r(st.get("score"), 0)})
            for i, st in enumerate((planned.compliance_detail or {}).get("steps") or [])
        ]
        out["sesion_planificada"] = _clean(
            {"titulo": planned.title, "cumplimiento_pct": _r(planned.compliance_score, 0), "pasos": steps}
        )
    if a.gear_id:
        gear = session.get(Gear, a.gear_id)
        out["zapatillas"] = gear.name if gear else None
    try:
        from app.services.routes import route_for_activity

        route = route_for_activity(session, user_id, a.id)
        if route:
            out["recorrido_repetido"] = {
                "nombre": route["name"],
                "veces": route["count"],
                "puesto_por_ritmo": route.get("rank"),
            }
    except Exception:  # noqa: BLE001 - dato secundario
        session.rollback()
    return f"Detalle de «{a.name or a.sport}» del {_ddmm(day)}", _clean(out)


def series_actividad(session: Session, user_id: int, args: dict) -> tuple[str, dict]:
    a = _owned_activity(session, user_id, args.get("id"))
    wanted = [c for c in (args.get("canales") or ["fc", "velocidad", "altitud"]) if c in SERIES_CHANNELS]
    if not wanted:
        raise ToolError(f"Canales disponibles: {', '.join(SERIES_CHANNELS)}.")
    ch = _channels(session, a.id, ["time", "distance", *(SERIES_CHANNELS[c] for c in wanted)])
    if not ch.get("time"):
        raise ToolError("Esta actividad no tiene datos segundo a segundo.")
    data = downsample(ch, MAX_SERIES_POINTS)
    points = []
    for i, t in enumerate(data["time"]):
        p = {
            "t": clock(t),
            "km": _r((data.get("distance") or [None] * (i + 1))[i] / 1000, 2)
            if data.get("distance") and data["distance"][i] is not None
            else None,
        }
        for c in wanted:
            v = (data.get(SERIES_CHANNELS[c]) or [None] * (i + 1))[i]
            p[c] = _speed_pace(v) if c == "velocidad" else _r(v, 0)
        points.append(_clean(p))
    label = f"Series ({', '.join(wanted)}) de «{a.name or a.sport}» del {_ddmm(local_day(a.start_time, a.timezone))}"
    return label, {"actividad_id": a.id, "nota": "velocidad expresada como ritmo min/km", "puntos": points}


def zonas_y_umbrales(session: Session, user_id: int, args: dict) -> tuple[str, dict]:
    from app.services.zones import effective_paces, zones_report

    rep = zones_report(session, user_id)
    cur = rep.get("current")
    out: dict = {}
    if cur:
        t = cur["thresholds"]
        out["vigentes_desde"] = str(cur["valid_from"])
        out["fc_umbral"] = t.get("lthr")
        out["fuente_fc_umbral"] = t.get("lthr_source")
        out["ritmo_umbral"] = pace(t.get("threshold_pace_s_km"))
        out["fuente_ritmo_umbral"] = t.get("pace_source")
        out["alternativas_ritmo_umbral"] = {k: pace(v) for k, v in (t.get("candidates") or {}).items()}
        out["zonas_fc"] = [{"zona": z["name"], "min": z["min"], "max": z["max"]} for z in cur["zones"].get("hr", [])]
        out["zonas_ritmo"] = [
            {"zona": z["name"], "rapido": pace(z["fast"]), "lento": pace(z["slow"])}
            for z in cur["zones"].get("pace", [])
        ]
    out["historial"] = [
        {
            "desde": str(h["valid_from"]),
            "fc_umbral": h["thresholds"].get("lthr"),
            "ritmo_umbral": pace(h["thresholds"].get("threshold_pace_s_km")),
        }
        for h in rep.get("history") or []
    ]
    from app.services.performance_tests import PROTOCOLS, summary_text, user_tests

    tests = [t for t in user_tests(session, user_id, limit=10) if t.status != "failed"]
    if tests:
        out["tests"] = [
            {"fecha": str(t.test_date), "tipo": PROTOCOLS[t.protocol].label if t.protocol in PROTOCOLS else t.protocol,
             "deporte": t.sport, "estado": "aplicado" if t.status == "confirmed" else "sin confirmar",
             "resultado": summary_text(t)}
            for t in tests
        ]  # fmt: skip
    eff = effective_paces(session, user_id)
    if eff:
        out["ritmos_entrenamiento"] = {k: f"{clock(v[0])}–{clock(v[1])}/km" for k, v in eff["paces"].items()}
        out["base_ritmos"] = eff["basis"]
        out["vdot"] = eff["vdot"]
    return "Tus zonas y umbrales", _clean(out)


METRICS_PROGRESION = ("forma", "volumen", "vo2max", "fc_reposo", "hrv", "sueno", "eficiencia", "curva_ritmos", "peso")


def progresion(session: Session, user_id: int, args: dict) -> tuple[str, dict]:
    from app.services.pace_curve import build_pace_curve

    metric = args.get("metrica")
    days = max(7, min(int(args.get("dias") or 90), 730))
    today = date.today()
    since = today - timedelta(days=days)
    activities = prog.user_activities(session, user_id)
    if metric == "forma":
        per_day, _ = prog.loads_by_day(
            activities, prog.user_thresholds(session, user_id), prog.user_rpes(session, user_id)
        )
        series = prog.fitness_series(per_day, since, today)
        step = max(1, len(series) // 60)
        data = [
            {"dia": str(p["day"]), "forma_ctl": p["ctl"], "fatiga_atl": p["atl"], "frescura_tsb": p["tsb"]}
            for p in series[::step]
        ]
    elif metric == "volumen":
        _, loads = prog.loads_by_day(
            activities, prog.user_thresholds(session, user_id), prog.user_rpes(session, user_id)
        )
        weeks = prog.weekly_volume(activities, loads, prog.week_start(since), prog.week_start(today))
        data = [
            {
                "semana": str(w["week"]),
                "km": round(w["distance_m"] / 1000, 1),
                "horas": round(w["duration_s"] / 3600, 1),
                "sesiones": w["count"],
                "carga": w["load"],
            }
            for w in weeks
        ]
    elif metric == "eficiencia":
        data = [
            {
                "dia": str(local_day(a.start_time, a.timezone)),
                "id": a.id,
                "m_min_por_ppm": v,
                "ritmo": _pace_of(a.distance_m, a.moving_duration_s or a.duration_s),
                "fc_media": _r(a.avg_hr, 0),
            }
            for a in activities
            if local_day(a.start_time, a.timezone) >= since and (v := prog.efficiency(a)) is not None
        ]
    elif metric == "curva_ritmos":
        curve = build_pace_curve(session, activities, days, today)
        data = [
            _clean(
                {
                    "duracion_s": d["seconds"],
                    "mejor": pace((d.get("best") or {}).get("pace_s_km")),
                    "periodo_anterior": pace((d.get("previous") or {}).get("pace_s_km")),
                }
            )
            for d in curve.get("durations", [])
        ]
    elif metric in ("vo2max", "fc_reposo", "hrv", "sueno", "peso"):
        key = {
            "vo2max": "vo2max",
            "fc_reposo": "resting_hr",
            "hrv": "hrv_last_night",
            "sueno": "sleep_seconds",
            "peso": "weight_kg",
        }[metric]
        series = prog.metric_series(session, user_id, key, since)
        data = [
            {"dia": str(p["day"]), "valor": _r(p["value"] / 3600 if metric == "sueno" else p["value"], 1)}
            for p in series
        ][-120:]
    else:
        raise ToolError(f"Métrica no válida. Opciones: {', '.join(METRICS_PROGRESION)}.")
    unit = {"sueno": "horas", "eficiencia": "metros por minuto por pulsación (más alto = mejor)"}.get(metric)
    return f"Progresión: {metric} ({days} días)", _clean({"metrica": metric, "unidad": unit, "datos": data})


def marcas_y_previsiones(session: Session, user_id: int, args: dict) -> tuple[str, dict]:
    from app.services.race_forecast import forecast, training_data
    from app.services.zones import effective_paces

    activities = prog.user_activities(session, user_id)
    records = []
    for r in prog.records(activities):
        if r["best"]:
            records.append(
                {
                    "distancia": r["label"],
                    "mejor": clock(r["best"]["time_s"]),
                    "fecha": str(r["best"]["day"]),
                    "actividad_id": r["best"]["activity_id"],
                    "veces_batido": len(r["history"]),
                }
            )
    data = training_data(activities, date.today())
    previsiones = {}
    for label, meters in (("5 km", 5000), ("10 km", 10000), ("media", 21097.5), ("maraton", 42195)):
        f = forecast(meters, data)
        if f.probable_s:
            previsiones[label] = {
                "probable": clock(f.probable_s),
                "rango": f"{clock(f.optimistic_s)}–{clock(f.conservative_s)}",
            }
    eff = effective_paces(session, user_id)
    return "Tus marcas y previsiones", _clean(
        {
            "marcas": records,
            "previsiones": previsiones,
            "vdot": eff["vdot"] if eff else None,
            "base_vdot": eff["basis"] if eff else None,
            "marcas_de_carreras_a_tope": data.from_races,
            "avisos": forecast(10000, data).warnings,
        }
    )


def _hms(seconds: float | None) -> str | None:
    if not seconds:
        return None
    total = round(seconds)
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


def _route_brief(session: Session, route_id: int | None) -> dict | None:
    from app.models import PlannedRoute
    from app.services.route_planner import summary

    route = session.get(PlannedRoute, route_id) if route_id else None
    return summary(route) if route else None


def ruta_planificada(session: Session, user_id: int, args: dict) -> tuple[str, dict]:
    """Una ruta del mapa con su perfil por tramos de 1 km y sus superficies (o la lista si no hay id)."""
    from app.models import PlannedRoute
    from app.services.route_planner import MODE_LABELS, summary

    route_id = args.get("id")
    if not route_id:
        rows = session.exec(
            select(PlannedRoute).where(PlannedRoute.user_id == user_id).order_by(col(PlannedRoute.created_at).desc())
        ).all()
        return "Tus rutas", {"rutas": [summary(r) for r in rows[:30]]}
    route = session.get(PlannedRoute, int(route_id))
    if route is None or route.user_id != user_id:
        raise ToolError("Esa ruta no existe.")
    # Perfil por kilómetro: altitud al final de cada km y desnivel del tramo.
    tramos, last_alt, km, gain, loss = [], None, 1, 0.0, 0.0
    for dist, alt in route.profile:
        if last_alt is not None:
            gain += max(0.0, alt - last_alt)
            loss += max(0.0, last_alt - alt)
        last_alt = alt
        if dist >= km * 1000:
            tramos.append({"km": km, "altitud_m": round(alt), "sube_m": round(gain), "baja_m": round(loss)})
            km, gain, loss = km + 1, 0.0, 0.0
    return f"Ruta {route.name}", {
        **summary(route),
        "modo": MODE_LABELS.get(route.mode, route.mode),
        "tiempo_estimado": _hms(route.estimated_s),
        "superficies": route.surfaces,
        "tipos_de_via": route.waytypes,
        "por_km": tramos[:60],
    }


def plan_y_objetivos(session: Session, user_id: int, args: dict) -> tuple[str, dict]:
    from app.services.race_forecast import goal_forecast
    from app.services.training_plans import active_plan, report

    today = date.today()
    desde = _day(args.get("desde"), today - timedelta(days=14))
    hasta = _day(args.get("hasta"), today + timedelta(days=14))
    sessions = session.exec(
        select(PlannedSession)
        .where(PlannedSession.user_id == user_id, PlannedSession.day >= desde, PlannedSession.day <= hasta)
        .order_by(PlannedSession.day)
    ).all()
    out: dict = {
        "sesiones": [
            _clean(
                {
                    "id": s.id,
                    "fecha": str(s.day),
                    "titulo": s.title,
                    "deporte": s.sport,
                    "tipo": s.session_kind,
                    "hecha_actividad_id": s.activity_id,
                    "cumplimiento_pct": _r(s.compliance_score, 0),
                    "ruta": _route_brief(session, s.planned_route_id),
                }
            )
            for s in sessions
        ]
    }
    plan = active_plan(session, user_id)
    if plan:
        rep = report(session, plan, today)
        out["plan_automatico"] = _clean(
            {
                "objetivo": rep["goal_name"],
                "carrera": rep["race_date"],
                "semana_actual": rep["current_week"],
                "semanas": [
                    _clean(
                        {
                            "n": w["index"],
                            "inicio": w["start"],
                            "fase": w["phase_label"],
                            "km_objetivo": w["target_km"],
                            "km_hechos": w["done_km"],
                            "descarga": w["is_recovery"] or None,
                            "ajuste": (w["adjustment"] or {}).get("reason"),
                        }
                    )
                    for w in rep["weeks"]
                ],
            }
        )
    goals = session.exec(select(RaceGoal).where(RaceGoal.user_id == user_id).order_by(RaceGoal.race_date)).all()
    out["objetivos"] = []
    for g in goals:
        if (g.race_date - today).days < -60:
            continue
        f = goal_forecast(session, g)
        out["objetivos"].append(
            _clean(
                {
                    "id": g.id,
                    "nombre": g.name,
                    "fecha": str(g.race_date),
                    "km": _r(g.distance_m / 1000, 2),
                    "objetivo": clock(g.target_time_s),
                    "prevision": clock(f.probable_s),
                    "rango": f"{clock(f.optimistic_s)}–{clock(f.conservative_s)}" if f.probable_s else None,
                    "resultado": clock(g.result_time_s),
                    "lugar": g.location_name,
                }
            )
        )
    return "Tu plan y objetivos", _clean(out)


def dia_de_carrera(session: Session, user_id: int, args: dict) -> tuple[str, dict]:
    from app.services.race_day import report

    try:
        goal = session.get(RaceGoal, int(args.get("objetivo_id")))
    except (TypeError, ValueError) as exc:
        raise ToolError("objetivo_id debe ser un número.") from exc
    if goal is None or goal.user_id != user_id:
        raise ToolError("No existe ese objetivo. Mira los ids con plan_y_objetivos.")
    rep = report(session, goal)
    if not rep.get("available"):
        return f"Día de carrera: {goal.name}", {"no_disponible": rep.get("reason")}
    w = rep.get("weather") or {}
    return f"Día de carrera: {goal.name}", _clean(
        {
            "prevision_base": clock(rep["base_s"]),
            "prevision_ajustada": clock(rep["adjusted_s"]),
            "efecto_calor_pct": rep["heat_pct"],
            "efecto_desnivel_pct": rep["elevation_pct"],
            "clima": _clean({k: w.get(k) for k in ("label", "temp_c", "dew_point_c", "humidity_pct", "wind_kmh")}),
            "ritmo_por_km": [pace(p["pace_s_km"]) for p in rep["pacing"]],
            "avituallamiento": _clean(
                {
                    "geles": rep["fueling"]["gels"],
                    "minutos": rep["fueling"]["gel_times_min"],
                    "liquido_ml_h": rep["fueling"]["fluid_ml_h"],
                }
            ),
        }
    )


# Clave del catálogo → nombre para la IA. Las «_min» se pasan de segundos a minutos.
SALUD_NAMES = {
    "resting_hr": "fc_reposo",
    "hrv_last_night": "hrv_ms",
    "sleep_seconds": "sueno_h",
    "sleep_score": "nota_sueno",
    "body_battery_max": "body_battery",
    "stress_avg": "estres",
    "steps_daily": "pasos",
    "lt_speed": "umbral_garmin",
    "lt_hr": "fc_umbral_garmin",
    "readiness_score": "preparacion",
    "temperature_deviation": "temp_desviacion_c",
    "temperature_trend_deviation": "temp_tendencia_c",
    "sleep_deep_s": "profundo_min",
    "sleep_rem_s": "rem_min",
    "sleep_light_s": "ligero_min",
    "sleep_awake_s": "despierto_min",
    "sleep_latency_s": "latencia_min",
    "sleep_efficiency": "eficiencia_sueno",
    "naps_s": "siestas_min",
    "avg_hr_sleep": "fc_media_noche",
    "breath_rate": "respiracion_rpm",
    "spo2_avg": "spo2",
    "breathing_disturbance_index": "alteraciones_respiratorias",
    "stress_high_s": "estres_alto_min",
    "recovery_high_s": "recuperacion_alta_min",
    "resilience_level": "resiliencia_1a5",
    "activity_score": "nota_actividad",
    "active_calories": "kcal_activas",
    "high_activity_time_s": "actividad_alta_min",
    "medium_activity_time_s": "actividad_media_min",
    "sedentary_time_s": "sedentario_min",
    "vo2max_oura": "vo2max_oura",
    "cardio_age": "edad_cardiovascular",
}


def _salud_value(key: str, v: float) -> float | str | None:
    if key == "sleep_seconds":
        return round(v / 3600, 1)
    if key == "lt_speed":
        return _speed_pace(v)
    if SALUD_NAMES[key].endswith("_min"):
        return round(v / 60)
    if key in ("temperature_deviation", "temperature_trend_deviation", "breathing_disturbance_index"):
        return _r(v, 2)
    return _r(v, 0)


def salud_diaria(session: Session, user_id: int, args: dict) -> tuple[str, dict]:
    from app.models import HealthTag, User
    from app.services.health_views import rest_periods

    today = date.today()
    hasta = _day(args.get("hasta"), today)
    desde = _day(args.get("desde"), hasta - timedelta(days=14))
    if (hasta - desde).days > 120:
        desde = hasta - timedelta(days=120)
    rows = session.exec(
        select(DailyMetric)
        .where(DailyMetric.user_id == user_id, DailyMetric.day >= desde, DailyMetric.day <= hasta)
        .order_by(DailyMetric.day)
    ).all()
    days = []
    for r in rows:
        m = r.metrics or {}
        d: dict = {"dia": str(r.day)}
        for key, name in SALUD_NAMES.items():
            if m.get(key) is not None:
                d[name] = _salud_value(key, m[key])
        if len(d) > 1:
            days.append(d)
    out: dict = {"dias": days}
    tags = session.exec(
        select(HealthTag).where(HealthTag.user_id == user_id, HealthTag.day >= desde, HealthTag.day <= hasta)
    ).all()
    if tags:
        out["etiquetas"] = [_clean({"dia": str(t.day), "etiqueta": t.label, "nota": t.comment}) for t in tags[:60]]
    user = session.get(User, user_id)
    rest = rest_periods(session, user, desde, hasta) if user is not None else []
    if rest:
        out["modo_descanso"] = [{"desde": str(p["start_date"]), "hasta": str(p["end_date"] or "activo")} for p in rest]
    return f"Salud diaria del {_ddmm(desde)} al {_ddmm(hasta)}", out


def _curve(sample: dict | None) -> dict | None:
    """Curva nocturna resumida: mínimo, máximo, media y media de cada tercio de la noche."""
    values = [v for v in (sample or {}).get("items") or [] if isinstance(v, int | float)]
    if not values:
        return None
    third = max(1, len(values) // 3)
    parts = [values[:third], values[third : 2 * third], values[2 * third :]]
    return {
        "min": _r(min(values), 0),
        "max": _r(max(values), 0),
        "media": _r(sum(values) / len(values), 0),
        "por_tercios": [_r(sum(p) / len(p), 0) for p in parts if p],
    }


def _phases_summary(phases: str) -> dict:
    """Minutos por fase y despertares del hipnograma de 5 min (1 profundo, 2 ligero, 3 REM, 4 despierto)."""
    names = {"1": "profundo_min", "2": "ligero_min", "3": "rem_min", "4": "despierto_min"}
    out = {name: phases.count(code) * 5 for code, name in names.items()}
    out["despertares"] = sum(1 for a, b in zip(phases, phases[1:], strict=False) if b == "4" and a != "4")
    first_deep = phases.find("1")
    if first_deep >= 0:
        out["primer_profundo_min"] = first_deep * 5
    return out


def _night_period(p: dict) -> dict:
    def mins(key: str) -> int | None:
        return round(p[key] / 60) if isinstance(p.get(key), int | float) else None

    return _clean({
        "inicio": p.get("bedtime_start"), "fin": p.get("bedtime_end"), "sueno_min": mins("total_sleep_s"),
        "profundo_min": mins("deep_s"), "rem_min": mins("rem_s"), "ligero_min": mins("light_s"),
        "despierto_min": mins("awake_s"), "latencia_min": mins("latency_s"), "eficiencia": p.get("efficiency"),
        "fc_media": _r(p.get("avg_hr"), 0), "fc_minima": p.get("lowest_hr"), "hrv_media": _r(p.get("avg_hrv"), 0),
        "respiracion": _r(p.get("avg_breath"), 1), "periodos_inquietos": p.get("restless_periods"),
    })  # fmt: skip


def noche_detalle(session: Session, user_id: int, args: dict) -> tuple[str, dict]:
    from app.models import User
    from app.services.health_views import night

    user = session.get(User, user_id)
    day = _day(args.get("dia"), date.today())
    if user is None:
        raise ToolError("Usuario no encontrado.")
    n = night(session, user, day)
    if n["main"] is None and not n["naps"]:
        return f"Noche del {_ddmm(day)}", {"error": "No hay datos de sueño de esa noche."}
    readiness = n["readiness"] or {}
    data = _clean({
        "fuente": n["source"],
        "principal": _night_period(n["main"]) if n["main"] else None,
        "fases": _phases_summary(n["hypnogram"]["phases"]) if n["hypnogram"] else None,
        "fc_noche": _curve(n["hr"]),
        "hrv_noche": _curve(n["hrv"]),
        "siestas": [_night_period(p) for p in n["naps"]],
        "nota_sueno": n["sleep_score"],
        "contribuidores_sueno": n["sleep_contributors"],
        "preparacion": readiness.get("score"),
        "temp_desviacion_c": readiness.get("temperature_deviation"),
        "contribuidores_preparacion": readiness.get("contributors"),
        "spo2": (n["spo2"] or {}).get("average"),
        "hora_optima": (n["sleep_time"] or {}).get("recommendation"),
        "etiquetas": [t["label"] for t in n["tags"]],
    })  # fmt: skip
    return f"Noche del {_ddmm(day)}", data


def lesiones_y_material(session: Session, user_id: int, args: dict) -> tuple[str, dict]:
    from app.services.gear import list_gear
    from app.services.injury import injury_report

    inj = injury_report(session, user_id)
    return "Riesgo de lesión y zapatillas", _clean(
        {
            "estado": inj["status"],
            "resumen": inj["summary"],
            "km_7_dias": inj["week_km"],
            "comprobaciones": [
                {"que": c["title"], "estado": c["status"], "detalle": c["message"]} for c in inj["checks"]
            ],
            "zapatillas": [
                _clean(
                    {
                        "nombre": g["name"],
                        "km": g["total_km"],
                        "limite_km": g["alert_km"],
                        "estado": g["status"],
                        "predeterminadas": g["is_default"] or None,
                    }
                )
                for g in list_gear(session, user_id)
            ],
        }
    )


# ─── Catálogo para el modelo ─────────────────────────────────────────────────

_DATE = {"type": "string", "description": "Fecha AAAA-MM-DD"}

TOOLS: list[ToolSpec] = [
    ToolSpec(
        "buscar_actividades",
        "Lista actividades entre dos fechas (por defecto, los últimos 30 días) con id, distancia, tiempo, ritmo, "
        "FC media y máxima, desnivel, carga, Training Effect y cumplimiento del plan. Úsala para encontrar entrenos "
        "concretos o ver qué hizo en un periodo.",
        {
            "type": "object",
            "properties": {
                "desde": _DATE,
                "hasta": _DATE,
                "deporte": {"type": "string", "description": "running, cycling, strength_training, swimming…"},
                "texto": {"type": "string", "description": "Texto a buscar en el nombre"},
                "solo_carreras": {"type": "boolean", "description": "Solo carreras marcadas a tope"},
                "limite": {"type": "integer", "description": "Máximo de actividades (1–50)"},
            },
        },
    ),
    ToolSpec(
        "detalle_actividad",
        "Todo sobre una actividad: métricas del reloj, vueltas (ritmo, FC, cadencia), parciales por km, tiempo en "
        "cada zona de FC, desacople FC/ritmo, sensaciones (RPE), sesión planificada y su cumplimiento, zapatillas "
        "y si es un recorrido repetido.",
        {
            "type": "object",
            "properties": {"id": {"type": "integer", "description": "Id de la actividad"}},
            "required": ["id"],
        },
    ),
    ToolSpec(
        "series_actividad",
        "Series segundo a segundo (reducidas a ~300 puntos) de una actividad: fc, velocidad (como ritmo), altitud, "
        "cadencia o potencia. Para ver cómo evolucionó el pulso o el ritmo dentro del entreno.",
        {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "Id de la actividad"},
                "canales": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(SERIES_CHANNELS)},
                    "description": "Canales a devolver",
                },
            },
            "required": ["id"],
        },
    ),
    ToolSpec(
        "zonas_y_umbrales",
        "Zonas de FC y de ritmo vigentes, FC y ritmo umbral con su fuente y alternativas, historial de cambios y "
        "ritmos de entrenamiento (E/M/T/I/R) y tus tests de rendimiento (umbral, VO2max, lactato, FTP, CSS).",
        {"type": "object", "properties": {}},
    ),
    ToolSpec(
        "progresion",
        "Evolución de una métrica: forma (CTL/ATL/TSB), volumen (semanal), vo2max, fc_reposo, hrv, sueno, "
        "eficiencia (ritmo a igual pulso), curva_ritmos (mejores ritmos por duración) o peso.",
        {
            "type": "object",
            "properties": {
                "metrica": {"type": "string", "enum": list(METRICS_PROGRESION)},
                "dias": {"type": "integer", "description": "Días hacia atrás (7–730, por defecto 90)"},
            },
            "required": ["metrica"],
        },
    ),
    ToolSpec(
        "marcas_y_previsiones",
        "Mejores marcas por distancia con fecha, previsiones de 5K/10K/media/maratón y nivel de carrera (VDOT).",
        {"type": "object", "properties": {}},
    ),
    ToolSpec(
        "plan_y_objetivos",
        "Sesiones planificadas en un rango (por defecto ±14 días) con su cumplimiento, el plan automático por "
        "semanas con sus ajustes y los objetivos de carrera con su previsión.",
        {"type": "object", "properties": {"desde": _DATE, "hasta": _DATE}},
    ),
    ToolSpec(
        "ruta_planificada",
        "Rutas que ha dibujado en el mapa (Plan → Rutas). Sin id, la lista; con id, su perfil km a km (altitud, "
        "subida y bajada), superficies, tipos de vía y tiempo estimado. Úsala para ajustar ritmos por pendiente, "
        "avituallamiento o la hora de salida de una sesión con ruta.",
        {"type": "object", "properties": {"id": {"type": "integer", "description": "Id de la ruta (opcional)"}}},
    ),
    ToolSpec(
        "dia_de_carrera",
        "Plan del día de carrera de un objetivo: previsión ajustada por clima y desnivel, ritmo por km y geles.",
        {"type": "object", "properties": {"objetivo_id": {"type": "integer"}}, "required": ["objetivo_id"]},
    ),
    ToolSpec(
        "salud_diaria",
        "Métricas diarias entre dos fechas (por defecto 14 días): FC en reposo, HRV, sueño y sus fases, siestas, "
        "preparación y temperatura (Oura), SpO2, Body Battery, estrés, resiliencia, actividad, pasos, umbral de "
        "Garmin, etiquetas (alcohol, enfermedad…) y periodos de modo descanso.",
        {"type": "object", "properties": {"desde": _DATE, "hasta": _DATE}},
    ),
    ToolSpec(
        "noche_detalle",
        "Detalle de una noche (por defecto la última): fases (profundo, REM, ligero, despierto, despertares), FC y "
        "HRV nocturnas resumidas, siestas, nota de sueño y de preparación con sus contribuidores, SpO2 y etiquetas. "
        "Fuente: la elegida por la persona (Oura o el reloj).",
        {"type": "object", "properties": {"dia": _DATE}},
    ),
    ToolSpec(
        "lesiones_y_material",
        "Avisos de riesgo de lesión (subida de volumen, monotonía, ACWR, tirada larga) y estado de las zapatillas.",
        {"type": "object", "properties": {}},
    ),
]

_BLOCK = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["warmup", "steady", "interval", "recovery", "cooldown"]},
        "repeat": {"type": "integer", "description": "Repeticiones (1 si no es una serie)"},
        "duration_s": {"type": "number", "description": "Duración en segundos (o distance_m)"},
        "distance_m": {"type": "number", "description": "Distancia en metros (o duration_s)"},
        "target_metric": {"type": "string", "enum": ["pace", "speed", "hr", "power", "cadence"]},
        "target_min": {"type": "number", "description": "Ritmo en s/km, FC en ppm, potencia en W…"},
        "target_max": {"type": "number"},
        "recovery_duration_s": {"type": "number", "description": "Recuperación entre repeticiones (s)"},
    },
    "required": ["kind", "repeat"],
}

COACH_TOOLS: list[ToolSpec] = [
    ToolSpec(
        "memoria_del_atleta",
        "Su ficha completa (lo que sabes de él más allá del reloj) con los ids de cada dato, si dio consentimiento "
        "para datos de salud y si hizo la entrevista inicial.",
        {"type": "object", "properties": {}},
    ),
    ToolSpec(
        "guardar_en_memoria",
        "Guarda en su ficha algo duradero que te ha CONTADO (no lo que deduces de los datos): historial, lesiones, "
        "salud, disponibilidad, preferencias, objetivos o vida diaria. Una frase clara en tercera persona, con fecha "
        "o época si la dijo. Para corregir un dato existente pasa reemplaza_id. Lesiones y salud solo si dio "
        "consentimiento.",
        {
            "type": "object",
            "properties": {
                "categoria": {"type": "string", "enum": list(coach.CATEGORIES)},
                "dato": {
                    "type": "string",
                    "description": "Ej.: «Tendinitis aquílea izquierda en primavera de 2025, ya recuperada»",
                },
                "reemplaza_id": {"type": "integer", "description": "Id del dato que corrige (opcional)"},
            },
            "required": ["categoria", "dato"],
        },
    ),
    ToolSpec(
        "actualizar_perfil",
        "Guarda en su perfil los datos que te ha DICHO y con los que la app calcula: fecha de nacimiento (FC máx. "
        "por edad y percentiles), sexo (percentiles), peso (calorías) y altura (IMC y zancada). Solo los campos "
        "que te haya dado; mira antes en memoria_del_atleta cuáles faltan.",
        {
            "type": "object",
            "properties": {
                "fecha_nacimiento": _DATE,
                "sexo": {"type": "string", "enum": ["male", "female"]},
                "peso_kg": {"type": "number"},
                "altura_cm": {"type": "number"},
            },
        },
    ),
    ToolSpec(
        "guardar_umbrales",
        "Guarda los valores de carrera que conoce de un test, una prueba de esfuerzo o su reloj: FC máxima, FC "
        "umbral, ritmo umbral o VO2max (quedan como test manual y ajustan sus zonas). Solo lo que te haya dicho, "
        "nunca estimaciones tuyas.",
        {
            "type": "object",
            "properties": {
                "fc_max": {"type": "integer", "description": "ppm"},
                "fc_umbral": {"type": "integer", "description": "ppm"},
                "ritmo_umbral": {"type": "string", "description": "min:s por km, p. ej. «4:35»"},
                "vo2max": {"type": "number", "description": "ml/kg/min"},
                "fecha": {"type": "string", "description": "AAAA-MM-DD del test (por defecto, hoy)"},
            },
        },
    ),
    ToolSpec(
        "olvidar_dato",
        "Borra un dato de su ficha (cuando te dice que ya no es así o que lo olvides).",
        {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
    ),
    ToolSpec(
        "terminar_entrevista",
        "Marca la entrevista inicial como hecha (cuando ya has preguntado lo esencial o él quiere parar).",
        {"type": "object", "properties": {}},
    ),
    ToolSpec(
        "proponer_cambio_plan",
        "Propone cambiar una sesión futura del plan (mover de día, cambiar título, notas o bloques). NO la cambia: "
        "la persona verá la propuesta y la aceptará o rechazará. Usa el id de plan_y_objetivos y explica el motivo.",
        {
            "type": "object",
            "properties": {
                "sesion_id": {"type": "integer"},
                "motivo": {"type": "string", "description": "Por qué (se le enseña tal cual)"},
                "nuevo_dia": _DATE,
                "nuevo_titulo": {"type": "string"},
                "notas": {"type": "string"},
                "bloques": {"type": "array", "items": _BLOCK, "description": "Bloques nuevos completos (opcional)"},
            },
            "required": ["sesion_id", "motivo"],
        },
    ),
]
# Solo lectura (análisis automáticos) y todas (chat con el entrenador).
READ_TOOLS = TOOLS
TOOLS = TOOLS + COACH_TOOLS
# Herramientas cuyo resultado lleva un «efecto» que se enseña en el chat (guardado, propuesta…).
EFFECT_TOOLS = {
    "guardar_en_memoria",
    "olvidar_dato",
    "actualizar_perfil",
    "guardar_umbrales",
    "terminar_entrevista",
    "proponer_cambio_plan",
}

_HANDLERS: dict[str, Callable[[Session, int, dict], tuple[str, dict]]] = {
    "buscar_actividades": buscar_actividades,
    "detalle_actividad": detalle_actividad,
    "series_actividad": series_actividad,
    "zonas_y_umbrales": zonas_y_umbrales,
    "progresion": progresion,
    "marcas_y_previsiones": marcas_y_previsiones,
    "plan_y_objetivos": plan_y_objetivos,
    "dia_de_carrera": dia_de_carrera,
    "ruta_planificada": ruta_planificada,
    "salud_diaria": salud_diaria,
    "noche_detalle": noche_detalle,
    "lesiones_y_material": lesiones_y_material,
    "memoria_del_atleta": coach.tool_memoria,
    "guardar_en_memoria": coach.tool_guardar,
    "olvidar_dato": coach.tool_olvidar,
    "actualizar_perfil": coach.tool_perfil,
    "guardar_umbrales": coach.tool_umbrales,
    "terminar_entrevista": coach.tool_terminar_entrevista,
    "proponer_cambio_plan": coach.tool_proponer,
}


def effect_of(name: str, result: str) -> dict | None:
    """El «efecto» de una herramienta de escritura, para enseñarlo en el chat."""
    if name not in EFFECT_TOOLS:
        return None
    try:
        return json.loads(result).get("efecto")
    except (ValueError, AttributeError):
        return None


def execute(session: Session, user_id: int, name: str, args: dict | None) -> tuple[str, str]:
    """
    Ejecuta una herramienta y devuelve (etiqueta para la interfaz, resultado en JSON para el modelo).
    Los errores se devuelven como texto para que el modelo pueda corregirse; nunca rompen la respuesta.
    """
    handler = _HANDLERS.get(name)
    if handler is None:
        return f"Herramienta desconocida: {name}", json.dumps({"error": f"No existe la herramienta {name}."})
    try:
        label, data = handler(session, user_id, args or {})
    except ToolError as exc:
        return f"{name}: {exc}", json.dumps({"error": str(exc)}, ensure_ascii=False)
    except Exception:  # noqa: BLE001 - un fallo interno no debe romper la conversación
        session.rollback()
        logger.exception("Fallo en la herramienta de IA %s", name)
        return f"{name}: no disponible", json.dumps({"error": "No se pudieron leer esos datos ahora."})
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + '…"} [resultado recortado: pide un rango más corto]'
    return label, text
