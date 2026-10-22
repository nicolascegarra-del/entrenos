"""
Análisis de la progresión con reglas basadas en literatura científica.

Cada sección produce un `Insight` con un estado (good / watch / alert / info / nodata),
un mensaje que cambia según tus datos y las referencias que lo respaldan. Las
funciones de cálculo son puras; `build_insights` reúne los datos del usuario.

Aviso: es información de entrenamiento, no consejo médico.
"""

import statistics
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from sqlmodel import Session, col, select

from app.models import Activity, ActivityStream, PlannedSession
from app.services import progress as prog
from app.services import race_forecast
from app.services.es_format import num as _n
from app.services.metric_catalog import RECORD_DISTANCES
from app.services.plan_steps import local_day, sport_family
from app.services.profile import age_on, get_profile, vo2max_percentile
from app.services.race_models import vdot
from app.services.strength import exercise_history, exercise_overview
from app.services.zones import effective_paces

# ─── Referencias (DOI verificados en Crossref) ───────────────────────────────


@dataclass(frozen=True)
class Evidence:
    label: str
    url: str | None = None


def _doi(label: str, doi: str) -> Evidence:
    return Evidence(label, f"https://doi.org/{doi}")


BANISTER = Evidence("Banister et al. 1975 · modelo impulso-respuesta (fitness-fatiga)")
COGGAN = Evidence("Allen y Coggan · Training and Racing with a Power Meter (Performance Manager)")
GABBETT = _doi("Gabbett 2016 · Br J Sports Med · paradoja entrenamiento-lesión", "10.1136/bjsports-2015-095788")
WILLIAMS = _doi(
    "Williams et al. 2016 · Br J Sports Med · ACWR con medias exponenciales", "10.1136/bjsports-2016-096589"
)
IMPELLIZZERI = _doi("Impellizzeri et al. 2020 · IJSPP · limitaciones del ACWR", "10.1123/ijspp.2019-0864")
NIELSEN = _doi("Nielsen et al. 2014 · JOSPT · progresión semanal y lesiones en corredores", "10.2519/jospt.2014.5164")
BUIST = _doi("Buist et al. 2007 · Am J Sports Med · la regla del 10 % no reduce lesiones", "10.1177/0363546507307505")
SEILER = _doi("Seiler 2010 · IJSPP · distribución de intensidad en resistencia", "10.1123/ijspp.5.3.276")
STOGGL = _doi("Stöggl y Sperlich 2014 · Front Physiol · entrenamiento polarizado", "10.3389/fphys.2014.00033")
BUCHHEIT = _doi("Buchheit 2014 · Front Physiol · seguimiento con medidas de FC", "10.3389/fphys.2014.00073")
KAMINSKY = _doi("Kaminsky et al. 2015 · Mayo Clin Proc · valores de referencia de VO2max (FRIEND)",
                "10.1016/j.mayocp.2015.07.026")  # fmt: skip
KODAMA = _doi("Kodama et al. 2009 · JAMA · capacidad cardiorrespiratoria y mortalidad", "10.1001/jama.2009.681")
FRIEL = Evidence("Friel · The Triathlete's Training Bible (desacople aeróbico Pa:FC)")
RIEGEL = Evidence("Riegel 1981 · American Scientist · Athletic records and human endurance")
DANIELS = Evidence("Daniels · Daniels' Running Formula (VDOT y ritmos de entrenamiento)")
TANDA = _doi("Tanda 2011 · J Hum Sport Exerc · predicción de maratón con índices de entrenamiento",
             "10.4100/jhse.2011.63.05")  # fmt: skip
WATSON = _doi("Watson et al. 2015 · J Clin Sleep Med · consenso AASM: ≥ 7 h de sueño", "10.5664/jcsm.4758")
MAH = _doi("Mah et al. 2011 · Sleep · más sueño mejora el rendimiento", "10.5665/SLEEP.1132")
BLAGROVE = _doi("Blagrove et al. 2017 · Sports Med · fuerza y economía de carrera", "10.1007/s40279-017-0835-7")

GOOD, WATCH, ALERT, INFO, NODATA = "good", "watch", "alert", "info", "nodata"


@dataclass
class Insight:
    status: str
    title: str
    message: str
    evidence: list[Evidence] = field(default_factory=list)


# ─── Cálculos puros ──────────────────────────────────────────────────────────


def ewma(loads: dict[date, float], start: date, end: date, span_days: int) -> dict[date, float]:
    """Media móvil exponencial con α = 2 / (N + 1), desde la primera carga hasta `end`."""
    if not loads:
        return {}
    alpha = 2 / (span_days + 1)
    value, out = 0.0, {}
    day = min(min(loads), start)
    while day <= end:
        value = alpha * loads.get(day, 0.0) + (1 - alpha) * value
        if day >= start:
            out[day] = value
        day += timedelta(days=1)
    return out


def acwr_series(loads: dict[date, float], start: date, end: date) -> list[dict]:
    """Relación carga aguda (7 d) : crónica (28 d) con medias exponenciales (Williams 2016)."""
    acute, chronic = ewma(loads, start, end, 7), ewma(loads, start, end, 28)
    return [{"day": d, "acwr": round(acute[d] / chronic[d], 2) if chronic[d] >= 1 else None} for d in sorted(chronic)]


def pct_change(current: float, baseline: float) -> float | None:
    return (current - baseline) / baseline * 100 if baseline > 0 else None


def intensity_split(activities: list[Activity]) -> dict[str, float]:
    """Segundos en baja (Z1–Z2), moderada (Z3) y alta (Z4–Z5) intensidad según las zonas de FC de Garmin."""
    zone = lambda a, i: a.metrics.get(f"hr_zone_{i}_s", 0.0)  # noqa: E731
    return {
        "low": sum(zone(a, 1) + zone(a, 2) for a in activities),
        "moderate": sum(zone(a, 3) for a in activities),
        "high": sum(zone(a, 4) + zone(a, 5) for a in activities),
    }


STEADY_SPEED_CV = 0.15  # por encima, la sesión tiene cambios de ritmo (series) y el desacople no aplica


def is_steady(channels: dict[str, list[float | None]]) -> bool:
    """¿Rodaje a ritmo constante? Coeficiente de variación de la velocidad en movimiento < 15 %."""
    speeds = [s for s in channels.get("speed") or [] if s and s > 0.5]
    if len(speeds) < 20:
        return False
    return statistics.pstdev(speeds) / statistics.fmean(speeds) < STEADY_SPEED_CV


def decoupling_pct(channels: dict[str, list[float | None]]) -> float | None:
    """
    Desacople aeróbico (Pa:FC): pérdida de eficiencia (velocidad/FC) de la 2.ª mitad frente a la 1.ª.
    Solo cuenta tramos en movimiento con FC. < 5 % sugiere buena base aeróbica.
    """
    time, speed, hr = channels.get("time") or [], channels.get("speed") or [], channels.get("hr") or []
    samples = [(t, s, h) for t, s, h in zip(time, speed, hr, strict=False) if t is not None and s and s > 0.5 and h]
    if len(samples) < 20:
        return None
    half = samples[-1][0] / 2
    first = [(s, h) for t, s, h in samples if t <= half]
    second = [(s, h) for t, s, h in samples if t > half]
    if len(first) < 10 or len(second) < 10:
        return None

    def ef(part: list[tuple[float, float]]) -> float:
        return statistics.fmean(s for s, _ in part) / statistics.fmean(h for _, h in part)

    ef1, ef2 = ef(first), ef(second)
    return round((ef1 - ef2) / ef1 * 100, 1)


# ─── Reglas por sección ──────────────────────────────────────────────────────


def fitness_insight(points: list[dict]) -> Insight:
    if len(points) < 8:
        return Insight(NODATA, "Forma física", "Necesito al menos una semana de datos para analizar tu forma física.")
    last, week_ago = points[-1], points[-8]
    ramp = last["ctl"] - week_ago["ctl"]
    tsb, label = last["tsb"], prog.form_label(last["tsb"])
    evidence = [BANISTER, COGGAN]
    if ramp > 8:
        return Insight(
            ALERT,
            f"Forma física subiendo muy rápido (+{_n(ramp, 1)}/semana)",
            f"Tu forma física ha subido {_n(ramp, 1)} puntos en 7 días. Subidas sostenidas por encima de "
            "5–8 por semana aumentan la fatiga acumulada; conviene una semana más suave pronto.",
            evidence,
        )
    if tsb < -30:
        return Insight(
            ALERT,
            "Fatiga alta",
            f"Tu frescura está en {_n(tsb, 0)}: la fatiga reciente supera con mucho a tu forma física. "
            "Prioriza descanso o sesiones suaves unos días.",
            evidence,
        )
    if ramp < -3 and last["ctl"] > 5:
        return Insight(
            WATCH,
            "Perdiendo forma física",
            f"Tu forma física ha bajado {_n(abs(ramp), 1)} puntos esta semana. Es normal en una descarga o un "
            "descanso; si no es intencionado, recupera la regularidad.",
            evidence,
        )
    if 0 < ramp <= 8:
        return Insight(
            GOOD,
            f"Progresión sostenible (+{_n(ramp, 1)}/semana) · {label}",
            f"Tu forma física sube a un ritmo asumible y tu frescura está en {_n(tsb, 0)} ({label.lower()}).",
            evidence,
        )
    return Insight(
        INFO,
        f"Estable · {label}",
        f"Tu forma física se mantiene ({_n(last['ctl'], 0)}) y tu frescura está en {_n(tsb, 0)}.",
        evidence,
    )


def acwr_insight(series: list[dict]) -> Insight:
    values = [p["acwr"] for p in series if p["acwr"] is not None]
    evidence = [GABBETT, WILLIAMS, IMPELLIZZERI]
    if not values:
        return Insight(NODATA, "Carga aguda : crónica", "Aún no hay suficiente historial de carga (≈ 4 semanas).")
    current = values[-1]
    if current > 1.5:
        return Insight(
            ALERT,
            f"Pico de carga (ACWR {_n(current, 2)})",
            "La carga de la última semana es más de 1,5 veces tu carga habitual. Los saltos bruscos se asocian a "
            "más riesgo de lesión; mejor aumentar de forma gradual.",
            evidence,
        )
    if current > 1.3:
        return Insight(
            WATCH,
            f"Carga en aumento (ACWR {_n(current, 2)})",
            "Estás entrenando algo por encima de tu carga habitual. Puede ser un bloque de trabajo planificado; "
            "vigila las sensaciones y la recuperación.",
            evidence,
        )
    if current < 0.8:
        return Insight(
            WATCH,
            f"Carga baja (ACWR {_n(current, 2)})",
            "Entrenas menos de lo habitual. Si no es una descarga planificada, perderás adaptaciones y el regreso "
            "brusco supondría un pico de carga.",
            evidence,
        )
    return Insight(
        GOOD,
        f"Carga equilibrada (ACWR {_n(current, 2)})",
        "Tu carga reciente está en línea con la habitual (zona 0,8–1,3). El ACWR es orientativo, no un predictor "
        "exacto de lesión.",
        evidence,
    )


def volume_insight(weeks: list[dict]) -> Insight:
    """Compara la última semana completa con la media de las 4 anteriores."""
    complete = weeks[:-1]  # la semana en curso aún no ha terminado
    if len(complete) < 5:
        return Insight(NODATA, "Volumen semanal", "Necesito al menos 5 semanas completas para comparar.")
    last = complete[-1]["distance_m"]
    baseline = statistics.fmean(w["distance_m"] for w in complete[-5:-1])
    change = pct_change(last, baseline)
    evidence = [NIELSEN, BUIST]
    if change is None:
        return Insight(INFO, "Volumen semanal", "Las semanas anteriores no tienen distancia para comparar.", evidence)
    km, base_km = last / 1000, baseline / 1000
    if change > 30:
        return Insight(
            ALERT,
            f"Subida de volumen del {_n(change, 0)} %",
            f"La semana pasada hiciste {_n(km, 1)} km frente a una media de {_n(base_km, 1)} km. Aumentos de más del "
            "30 % se han asociado a lesiones en corredores.",
            evidence,
        )
    if change < -40:
        return Insight(
            INFO,
            f"Semana de descarga ({_n(change, 0)} %)",
            f"{_n(km, 1)} km frente a una media de {_n(base_km, 1)} km. Bien si buscabas recuperar.",
            evidence,
        )
    if change < 0:
        return Insight(
            INFO,
            f"Volumen algo menor ({_n(change, 0)} %)",
            f"La semana pasada: {_n(km, 1)} km (media previa {_n(base_km, 1)} km). Bajada moderada, sin riesgo.",
            evidence,
        )
    return Insight(
        GOOD,
        f"Volumen progresivo ({_n(change, 0, sign=True)} %)",
        f"La semana pasada: {_n(km, 1)} km (media previa {_n(base_km, 1)} km). Cambio dentro de un rango prudente.",
        evidence,
    )


def intensity_insight(split: dict[str, float]) -> Insight:
    total = sum(split.values())
    evidence = [SEILER, STOGGL]
    if total < 3600:
        return Insight(
            NODATA, "Distribución de intensidad", "No hay suficiente tiempo con FC en las últimas 4 semanas."
        )
    low, high = split["low"] / total * 100, split["high"] / total * 100
    moderate = 100 - low - high
    detail = f"Últimas 4 semanas: {_n(low, 0)} % suave, {_n(moderate, 0)} % moderado, {_n(high, 0)} % intenso."
    note = " (Zonas de Garmin por % de FC máx.: una aproximación a los umbrales reales.)"
    if low >= 75:
        return Insight(GOOD, "Base suave sólida", detail + " Coincide con el ~80/20 de los deportistas de resistencia."
                       + note, evidence)  # fmt: skip
    if moderate > 35:
        return Insight(
            WATCH,
            "Mucho tiempo en zona media",
            detail + " Demasiado tiempo «ni suave ni duro» suele dar menos adaptaciones; haz los rodajes más suaves "
            "y los días duros de verdad." + note,
            evidence,
        )
    return Insight(
        WATCH,
        "Poca intensidad baja",
        detail + " Los deportistas de resistencia suelen hacer ~75–80 % del tiempo suave." + note,
        evidence,
    )


def resting_hr_insight(series: list[dict]) -> Insight:
    values = [p["value"] for p in series]
    evidence = [BUCHHEIT]
    if len(values) < 10:
        return Insight(NODATA, "FC en reposo", "Necesito al menos 10 días de FC en reposo.")
    baseline = statistics.median(values[-33:-3])
    recent = statistics.fmean(values[-3:])
    delta = recent - baseline
    if delta >= 5:
        return Insight(
            ALERT,
            f"FC en reposo elevada (+{_n(delta, 0)} ppm)",
            f"Los últimos 3 días ({_n(recent, 0)} ppm) están claramente por encima de tu referencia "
            f"({_n(baseline, 0)}). "
            "Suele indicar fatiga, estrés, mal sueño o una enfermedad incipiente: baja la intensidad.",
            evidence,
        )
    if delta >= 3:
        return Insight(
            WATCH,
            f"FC en reposo algo alta (+{_n(delta, 0)} ppm)",
            f"{_n(recent, 0)} ppm frente a tu referencia de {_n(baseline, 0)}. Vigila el descanso.",
            evidence,
        )
    return Insight(
        GOOD,
        "FC en reposo estable",
        f"{_n(recent, 0)} ppm (referencia {_n(baseline, 0)}). Sin señales de fatiga acumulada.",
        evidence,
    )


def _percentile_text(percentile: dict | None) -> str:
    if not percentile:
        return " Añade tu fecha de nacimiento y sexo en Ajustes para compararte con tu grupo de edad."
    where = {"below": "por debajo del percentil 5", "above": "por encima del percentil 95"}.get(
        percentile["bound"], f"en el percentil {percentile['percentile']}"
    )
    return (
        f" Para tu edad ({percentile['age_group']} años) y sexo estás {where} "
        f"(la mediana es {_n(percentile['median'], 1)}; referencia medida en laboratorio, el reloj solo la estima)."
    )


def vo2max_insight(series: list[dict], percentile: dict | None = None) -> Insight:
    insight = _vo2max_trend(series)
    if insight.status != NODATA:
        insight.message += _percentile_text(percentile)
        insight.evidence = [*insight.evidence, KAMINSKY]
    return insight


def _vo2max_trend(series: list[dict]) -> Insight:
    values = [p["value"] for p in series]
    evidence = [KODAMA]
    if len(values) < 4:
        return Insight(NODATA, "VO2max", "Aún hay pocas estimaciones de VO2max en este periodo.")
    start, end = statistics.fmean(values[:3]), statistics.fmean(values[-3:])
    change = end - start
    mets = change / 3.5
    if change >= 1:
        return Insight(
            GOOD,
            f"VO2max al alza (+{_n(change, 1)})",
            f"De {_n(start, 0)} a {_n(end, 0)} ml/kg/min (+{_n(mets, 1)} MET). Cada MET de mejora se asocia "
            "a ~13 % menos "
            "de mortalidad por cualquier causa. La estimación del reloj tiene un margen de ±5 %.",
            evidence,
        )
    if change <= -1:
        return Insight(
            WATCH,
            f"VO2max a la baja ({_n(change, 1)})",
            f"De {_n(start, 0)} a {_n(end, 0)} ml/kg/min. Suele responder a más volumen suave y algo de "
            "trabajo intenso. "
            "Recuerda el margen de ±5 % de la estimación.",
            evidence,
        )
    return Insight(INFO, f"VO2max estable ({_n(end, 0)})", "Sin cambios relevantes dentro del margen de la estimación.",
                   evidence)  # fmt: skip


def efficiency_insight(points: list[dict], decoupling: list[dict]) -> Insight:
    evidence = [FRIEL]
    if len(points) < 6:
        return Insight(NODATA, "Eficiencia aeróbica", "Necesito al menos 6 carreras con FC.")
    recent = [p["value"] for p in points[-4:]]
    previous = [p["value"] for p in points[:-4]]
    change = pct_change(statistics.fmean(recent), statistics.fmean(previous))
    dec = [d["value"] for d in decoupling[-3:]]
    dec_text = ""
    if dec:
        avg_dec = statistics.fmean(dec)
        verdict = "buena base aeróbica" if avg_dec < 5 else "aún hay margen en la base aeróbica"
        dec_text = f" Desacople medio en tus tiradas largas: {_n(avg_dec, 1)} % ({verdict})."
    if change is not None and change >= 3:
        return Insight(GOOD, f"Más eficiente (+{_n(change, 0)} %)",
                       "Corres más rápido a la misma FC que antes: señal de adaptación aeróbica." + dec_text,
                       evidence)  # fmt: skip
    if change is not None and change <= -3:
        return Insight(WATCH, f"Menos eficiente ({_n(change, 0)} %)",
                       "A igual FC vas algo más lento. Puede deberse a fatiga, calor o terreno." + dec_text,
                       evidence)  # fmt: skip
    return Insight(INFO, "Eficiencia estable", "Tus últimas carreras rinden igual a la misma FC." + dec_text,
                   evidence)  # fmt: skip


def records_insight(source: dict | None) -> Insight:
    if source is None:
        return Insight(NODATA, "Predicciones", "No hay marcas recientes (≥ 3 km) para predecir tiempos.")
    return Insight(
        INFO,
        f"VDOT {_n(source['vdot'], 0)}",
        f"Basado en tu mejor {source['label'].lower()} reciente. Son tramos dentro de entrenamientos, no "
        "carreras: en competición probablemente irías más rápido.",
        [RIEGEL, DANIELS, TANDA],
    )


def recovery_insight(sleep_hours: list[float], rhr: Insight) -> Insight:
    evidence = [WATSON, MAH, BUCHHEIT]
    if len(sleep_hours) < 3:
        return Insight(NODATA, "Recuperación", "Faltan datos de sueño de los últimos días.")
    avg = statistics.fmean(sleep_hours[-7:])
    short = avg < 7
    if short and rhr.status in (WATCH, ALERT):
        return Insight(
            ALERT,
            "Recuperación comprometida",
            f"Duermes {_n(avg, 1)} h de media y tu FC en reposo está elevada. Prioriza dormir y suaviza los próximos "
            "entrenos.",
            evidence,
        )
    if short:
        return Insight(
            WATCH,
            f"Poco sueño ({_n(avg, 1)} h)",
            "Por debajo de las 7 h recomendadas para adultos; en deportistas, dormir más mejora el rendimiento.",
            evidence,
        )
    return Insight(GOOD, f"Buen descanso ({_n(avg, 1)} h)", "Duermes lo recomendado (≥ 7 h).", evidence)


def consistency_insight(weekly_sessions: list[int], compliance: float | None) -> Insight:
    if len(weekly_sessions) < 4:
        return Insight(NODATA, "Constancia", "Faltan semanas para valorar la regularidad.")
    avg = statistics.fmean(weekly_sessions[-4:])
    active = sum(1 for n in weekly_sessions[-4:] if n > 0)
    plan = f" Cumplimiento del plan: {_n(compliance, 0)} %." if compliance is not None else ""
    text = f"{_n(avg, 1)} sesiones/semana de media; {active} de las últimas 4 semanas con actividad.{plan}"
    if active == 4 and avg >= 3:
        return Insight(GOOD, "Muy constante", text + " La regularidad es la base de cualquier mejora.")
    if active >= 3:
        return Insight(INFO, "Constancia aceptable", text + " Una sesión más por semana marcaría diferencia.")
    return Insight(WATCH, "Poca regularidad", text + " Varias semanas sin entrenar hacen perder adaptaciones.")


def strength_insight(overview: list[dict], sessions_4w: int) -> Insight:
    evidence = [BLAGROVE]
    if not overview:
        return Insight(
            INFO,
            "Sin registro de fuerza",
            "Añade tus series a las sesiones de fuerza. En corredores, 2 sesiones/semana mejoran la "
            "economía de carrera.",
            evidence,
        )
    per_week = sessions_4w / 4
    best = max((e for e in overview if e["e1rm_change_kg"] is not None), key=lambda e: e["e1rm_change_kg"],
               default=None)  # fmt: skip
    trend = (
        f" Mayor progreso: {best['exercise']} ({_n(best['e1rm_change_kg'], 1, sign=True)} kg de 1RM)." if best else ""
    )
    status = GOOD if per_week >= 1.5 else WATCH
    return Insight(
        status,
        f"{_n(per_week, 1)} sesiones de fuerza/semana",
        f"Recomendado ~2 por semana para mejorar la economía de carrera.{trend}",
        evidence,
    )


def overall(sections: dict[str, Insight]) -> list[dict]:
    """Semáforo general: carga, recuperación, constancia y tendencia aeróbica (el peor estado de cada grupo)."""
    rank = {ALERT: 3, WATCH: 2, GOOD: 1, INFO: 1, NODATA: 0}
    groups = {
        "Carga": ["fitness", "acwr", "volume"],
        "Recuperación": ["recovery", "resting_hr"],
        "Constancia": ["consistency"],
        "Tendencia aeróbica": ["efficiency", "vo2max", "intensity"],
    }
    result = []
    for label, keys in groups.items():
        items = [sections[k] for k in keys if k in sections and sections[k].status != NODATA]
        if not items:
            result.append({"label": label, "status": NODATA, "title": "Sin datos"})
            continue
        worst = max(items, key=lambda i: rank[i.status])
        status = GOOD if worst.status == INFO else worst.status
        result.append({"label": label, "status": status, "title": worst.title})
    return result


# ─── Orquestación ────────────────────────────────────────────────────────────


def _record_source(activities: list[Activity], since: date) -> dict | None:
    """Mejor marca reciente (≥ 3 km) para predicciones: la de mayor VDOT."""
    best = None
    for a in activities:
        if local_day(a.start_time, a.timezone) < since:
            continue
        for key, distance in RECORD_DISTANCES.items():
            time_s = a.metrics.get(key)
            if time_s and distance >= 3000:
                value = vdot(distance, time_s)
                if best is None or value > best["vdot"]:
                    best = {"key": key, "distance_m": distance, "time_s": time_s, "vdot": value}
    return best


def _user_percentile(session: Session, user_id: int, vo2_series: list[dict]) -> dict | None:
    profile = get_profile(session, user_id)
    if not (vo2_series and profile.birth_date and profile.sex):
        return None
    return vo2max_percentile(vo2_series[-1]["value"], age_on(profile.birth_date, date.today()), profile.sex)


def build_insights(session: Session, user_id: int, days: int) -> dict:
    today = date.today()
    since = today - timedelta(days=days)
    activities = prog.user_activities(session, user_id)
    thresholds = prog.user_thresholds(session, user_id)
    per_day, per_activity = prog.loads_by_day(activities, thresholds, prog.user_rpes(session, user_id))

    fitness_points = prog.fitness_series(per_day, since, today)
    acwr = acwr_series(per_day, since, today)
    last_monday = prog.week_start(today)
    weeks = prog.weekly_volume(activities, per_activity, last_monday - timedelta(weeks=8), last_monday)

    four_weeks = [a for a in activities if local_day(a.start_time, a.timezone) >= today - timedelta(days=28)]
    split = intensity_split(four_weeks)
    intensity_weeks = []
    for w in weeks[-8:]:
        acts = [a for a in activities if prog.week_start(local_day(a.start_time, a.timezone)) == w["week"]]
        s = intensity_split(acts)
        intensity_weeks.append({"week": w["week"], **{k: round(v / 60) for k, v in s.items()}})

    rhr_series = prog.metric_series(session, user_id, "resting_hr", today - timedelta(days=40))
    vo2_series = prog.metric_series(session, user_id, "vo2max", since)
    sleep = prog.metric_series(session, user_id, "sleep_seconds", today - timedelta(days=10))

    efficiency_points = [
        {"day": local_day(a.start_time, a.timezone), "value": v, "activity_id": a.id}
        for a in activities
        if local_day(a.start_time, a.timezone) >= since and (v := prog.efficiency(a)) is not None
    ]
    long_runs = [
        a for a in activities
        if sport_family(a.sport) == "running" and a.duration_s >= 45 * 60 and a.avg_hr
        and local_day(a.start_time, a.timezone) >= since
    ][-8:]  # fmt: skip
    decoupling = []
    for a in long_runs:
        streams = session.exec(
            select(ActivityStream).where(
                ActivityStream.activity_id == a.id, col(ActivityStream.channel).in_(["time", "speed", "hr"])
            )
        ).all()
        channels = {s.channel: s.values for s in streams}
        value = decoupling_pct(channels) if is_steady(channels) else None
        if value is not None:
            decoupling.append({"day": local_day(a.start_time, a.timezone), "activity_id": a.id, "value": value})

    source = _record_source(activities, today - timedelta(days=180))
    predictions, paces = [], None
    if source:
        source["label"] = next(lbl for k, lbl in (
            ("best_5k", "5 km"), ("best_10k", "10 km"), ("best_half", "Media maratón"), ("best_marathon", "Maratón"),
            ("best_mile", "Milla"), ("best_1k", "1 km")) if k == source["key"])  # fmt: skip
        # Mismo motor que Objetivos (Riegel personal + VDOT + Tanda en maratón) para que no se contradigan.
        data = race_forecast.training_data(activities, today)
        calibration = race_forecast.user_calibration(session, user_id)
        for label, meters in (("5 km", 5000), ("10 km", 10000), ("Media maratón", 21097.5), ("Maratón", 42195)):
            t = race_forecast.forecast(meters, data, calibration).probable_s
            if t:
                predictions.append(
                    {"label": label, "distance_m": meters, "time_s": t, "pace_s_km": round(t / meters * 1000)}
                )
    # Mismos ritmos que el planificador: del umbral efectivo si es más rápido que tus marcas.
    eff = effective_paces(session, user_id, today)
    if eff:
        p = eff["paces"]
        paces = {
            "easy": list(p["easy"]),
            "threshold": round(sum(p["threshold"]) / 2),
            "interval": round(sum(p["interval"]) / 2),
            **{
                k: eff[k]
                for k in (
                    "vdot",
                    "basis",
                    "vdot_marks",
                    "vdot_from_races",
                    "threshold_pace_s_km",
                    "threshold_source",
                    "alternatives",
                )
            },
        }

    sessions_per_week = [w["count"] for w in weeks[:-1]]
    compliance_rows = session.exec(
        select(PlannedSession.compliance_score).where(
            PlannedSession.user_id == user_id,
            PlannedSession.day >= today - timedelta(days=28),
            col(PlannedSession.compliance_score).is_not(None),
        )
    ).all()
    compliance = statistics.fmean(compliance_rows) if compliance_rows else None

    history = exercise_history(session, user_id)
    strength_sessions = len({
        s["activity_id"] for sessions in history.values() for s in sessions if s["day"] >= today - timedelta(days=28)
    })  # fmt: skip

    rhr = resting_hr_insight(rhr_series)
    sections = {
        "fitness": fitness_insight(fitness_points),
        "acwr": acwr_insight(acwr),
        "volume": volume_insight(weeks),
        "intensity": intensity_insight(split),
        "resting_hr": rhr,
        "vo2max": vo2max_insight(vo2_series, _user_percentile(session, user_id, vo2_series)),
        "efficiency": efficiency_insight(efficiency_points, decoupling),
        "records": records_insight(source),
        "recovery": recovery_insight([p["value"] / 3600 for p in sleep], rhr),
        "consistency": consistency_insight(sessions_per_week, compliance),
        "strength": strength_insight(exercise_overview(history), strength_sessions),
    }
    return {
        "overall": overall(sections),
        "sections": {k: asdict(v) for k, v in sections.items()},
        "acwr": acwr,
        "intensity": {
            "split_min": {k: round(v / 60) for k, v in split.items()},
            "weeks": intensity_weeks,
        },
        "decoupling": decoupling,
        "predictions": predictions,
        "training_paces": paces,
        "disclaimer": "Información orientativa basada en literatura deportiva; no sustituye el consejo de un "
        "profesional sanitario.",
    }
