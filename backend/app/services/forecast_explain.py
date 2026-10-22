"""
Explicaciones en lenguaje natural de la previsión de carrera y de los ritmos de
entrenamiento: qué datos se usan, qué dice cada modelo, por qué el rango, qué ha
cambiado y qué falta para el objetivo. Cada texto se apoya en sus fuentes.
"""

from dataclasses import asdict, dataclass
from datetime import date

from app.services.es_format import num
from app.services.insights import DANIELS, RIEGEL, SEILER, TANDA
from app.services.race_forecast import (
    MARATHON_M,
    TANDA_MIN_KM_WEEK,
    VDOT_GAIN_PER_WEEK,
    Forecast,
    TrainingData,
    forecast,
    readiness_targets,
)
from app.services.race_models import DANIELS_FRACTIONS, DEFAULT_RIEGEL_EXPONENT

RECORD_LABELS = {1000: "1 km", 1609: "milla", 5000: "5 km", 10000: "10 km", 21098: "media maratón",
                 42195: "maratón"}  # fmt: skip


@dataclass
class Point:
    title: str
    text: str


def _clock(seconds: float) -> str:
    s = round(seconds)
    h, m, sec = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def _date(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def _distance(meters: float) -> str:
    label = RECORD_LABELS.get(round(meters))
    return label or f"{num(meters / 1000, 1).removesuffix(',0')} km"


def _km(meters: float) -> str:
    """Kilómetros con un decimal y sin ",0" sobrante: 15000 → "15", 11200 → "11,2"."""
    return num(meters / 1000, 1).removesuffix(",0")


def loss_per_doubling(exponent: float) -> float:
    """% que empeora el ritmo cada vez que se dobla la distancia según el exponente de Riegel."""
    return (2 ** (exponent - 1) - 1) * 100


def _starting_point(f: Forecast, data: TrainingData) -> Point | None:
    if f.vdot_source == "marca" and f.source_distance_m and f.source_time_s and f.source_day:
        pace = f.source_time_s / f.source_distance_m * 1000
        return Point(
            "Tu punto de partida",
            f"La referencia es tu mejor {_distance(f.source_distance_m)} reciente: {_clock(f.source_time_s)} "
            f"el {_date(f.source_day)} ({_clock(pace)} /km), que equivale a un VDOT de {num(f.vdot_current, 1)}. "
            "De todas tus marcas de 3 km o más de los últimos 6 meses es la que indica mejor forma. "
            "Son tramos dentro de entrenamientos (Garmin detecta tus mejores kilómetros), no carreras: en "
            "competición, con dorsal y descansado, lo normal es ir algo más rápido.",
        )
    if f.vdot_source == "vo2max":
        return Point(
            "Tu punto de partida",
            f"No hay marcas recientes de 3 km o más, así que se usa el VO2max que estima tu reloj "
            f"({num(f.vdot_current, 0)}) como aproximación al VDOT. Es la base menos fiable: en cuanto corras "
            "algún 5 km o 10 km rápido, la previsión mejorará mucho.",
        )
    return None


def _fatigue(f: Forecast, data: TrainingData) -> Point:
    distances = [_distance(d) for d in sorted({d for d, _, _ in data.efforts.values()})]
    if f.exponent_personal and f.exponent:
        loss = loss_per_doubling(f.exponent)
        standard = loss_per_doubling(DEFAULT_RIEGEL_EXPONENT)
        profile = (
            "pierdes más ritmo que la media al alargar la distancia: eres relativamente más rápido en corto "
            "que resistente en largo; el volumen y las tiradas largas son tu margen de mejora"
            if f.exponent > DEFAULT_RIEGEL_EXPONENT + 0.01
            else "mantienes el ritmo mejor que la media al alargar la distancia: tienes buena resistencia"
            if f.exponent < DEFAULT_RIEGEL_EXPONENT - 0.01
            else "pierdes ritmo al alargar la distancia como la media de corredores"
        )
        return Point(
            "Cómo pierdes ritmo con la distancia",
            f"Con tus mejores marcas en {', '.join(distances)}, tu ritmo empeora un {num(loss, 1)} % cada vez que "
            f"doblas la distancia (exponente {num(f.exponent, 3)}; la referencia general de Riegel es "
            f"{num(DEFAULT_RIEGEL_EXPONENT, 2)}, ≈ {num(standard, 1)} %). Es decir, {profile}.",
        )
    return Point(
        "Cómo pierdes ritmo con la distancia",
        "Tus marcas no cubren distancias lo bastante distintas (hace falta al menos ×3, p. ej. 3 km y 10 km) "
        "para calcular tu propio perfil, así que se usa el exponente general de Riegel "
        f"({num(DEFAULT_RIEGEL_EXPONENT, 2)}, ≈ {num(loss_per_doubling(DEFAULT_RIEGEL_EXPONENT), 1)} % más lento "
        "al doblar la distancia).",
    )


def _models(f: Forecast, distance_m: float, data: TrainingData) -> Point:
    parts = [f"{m.label}: {_clock(m.time_s)} ({round(m.weight * 100)} %)" for m in f.models]
    text = "La previsión combina varios modelos para no depender de uno solo — " + "; ".join(parts) + "."
    if abs(distance_m - MARATHON_M) < 1000:
        if any(m.key == "tanda" for m in f.models):
            text += (
                " En maratón, Tanda pesa más porque el rendimiento depende sobre todo del volumen semanal y del "
                "ritmo medio de entrenamiento, más que de lo rápido que seas en distancias cortas."
            )
        else:
            text += (
                f" Tanda no se usa: con {num(data.km_per_week, 0)} km/semana estás por debajo de los "
                f"{TANDA_MIN_KM_WEEK} km/semana necesarios para que el modelo sea válido."
            )
    return Point("Qué dice cada modelo", text)


def _range(f: Forecast, data: TrainingData, distance_m: float) -> Point:
    reasons = []
    times = [m.time_s for m in f.models]
    if len(times) > 1 and f.probable_s:
        diff = (max(times) - min(times)) / f.probable_s * 100
        reasons.append(f"los modelos difieren entre sí un {num(diff, 0)} %")
    reasons.append("cuanto más larga es la carrera, más influyen el día, el calor y el ritmo de salida")
    if f.vdot_source == "marca" and not f.source_is_race:
        reasons.append("el lado optimista se amplía porque tus marcas son de entrenamiento")
    if data.longest_run_m and distance_m > data.longest_run_m * 1.05:
        reasons.append(
            f"aún no has corrido la distancia (tu tirada más larga es de {num(data.longest_run_m / 1000, 1)} km)"
        )
    spread = f"±{num((f.spread_pct or 0) * 100, 0)} %"
    return Point(
        "Por qué este rango",
        f"Entre {_clock(f.optimistic_s)} y {_clock(f.conservative_s)} ({spread}) porque " + "; ".join(reasons) + ".",
    )


def _reference(f: Forecast) -> str:
    if f.vdot_source == "marca" and f.source_distance_m and f.source_time_s and f.source_day:
        return (
            f"tu {_distance(f.source_distance_m)} de {_clock(f.source_time_s)} del {_date(f.source_day)} "
            f"(VDOT {num(f.vdot_current, 1)})"
        )
    return f"el VO2max del reloj ({num(f.vdot_current or 0, 0)})"


def _evolution(
    evolution: list[dict], then: TrainingData | None, now: TrainingData, distance_m: float, f_now: Forecast
) -> Point | None:
    """
    Explica el cambio de la previsión separando la causa principal (la marca de referencia,
    que es lo que más pesa en 5K–media) de los factores de entrenamiento que juegan a favor o en contra.
    """
    if len(evolution) < 2 or then is None:
        return None
    first, last = evolution[0], evolution[-1]
    delta = last["probable_s"] - first["probable_s"]
    weeks = round((last["day"] - first["day"]).days / 7)
    f_then = forecast(distance_m, then)

    main = None
    if f_then.vdot_current and f_now.vdot_current and abs(f_now.vdot_current - f_then.vdot_current) >= 0.2:
        same_mark = (f_then.source_distance_m, f_then.source_time_s) == (f_now.source_distance_m, f_now.source_time_s)
        if not same_mark:
            main = f"tu marca de referencia ha pasado de {_reference(f_then)} a {_reference(f_now)}"
            if f_now.vdot_current < f_then.vdot_current:
                main += ": la anterior ha quedado fuera de la ventana de 6 meses, que da prioridad a tu forma reciente"
    if main is None and (f_then.exponent or 0) and abs((f_now.exponent or 0) - (f_then.exponent or 0)) >= 0.01:
        main = (
            f"tu forma de perder ritmo con la distancia ha cambiado (exponente de {num(f_then.exponent, 3)} a "
            f"{num(f_now.exponent, 3)})"
        )

    favour, against = [], []
    if now.km_per_week - then.km_per_week >= 3:
        favour.append(f"has subido el volumen de {num(then.km_per_week, 0)} a {num(now.km_per_week, 0)} km/semana")
    elif then.km_per_week - now.km_per_week >= 3:
        against.append(f"has bajado el volumen de {num(then.km_per_week, 0)} a {num(now.km_per_week, 0)} km/semana")
    if now.longest_run_m - then.longest_run_m >= 1000:
        favour.append(f"tu tirada más larga ha pasado de {_km(then.longest_run_m)} a {_km(now.longest_run_m)} km")

    if abs(delta) < 15:
        text = f"En las últimas {weeks} semanas la previsión apenas ha cambiado ({_clock(last['probable_s'])})."
    else:
        verb = "mejorado" if delta < 0 else "empeorado"
        text = (
            f"Hace {weeks} semanas la previsión era {_clock(first['probable_s'])} y ahora es "
            f"{_clock(last['probable_s'])}: ha {verb} {_clock(abs(delta))}."
        )
        if main:
            text += f" El motivo principal: {main}."
    if favour:
        text += " A tu favor: " + " y ".join(favour) + "."
        if abs(distance_m - MARATHON_M) >= 1000:
            text += (
                " En distancias hasta la media pesa sobre todo lo rápido que corres, así que este trabajo se notará "
                "cuando lo conviertas en marcas mejores (un test de 5K o 10K actualizaría la previsión)."
            )
    if against:
        text += " En contra: " + " y ".join(against) + "."
    return Point("Cómo ha evolucionado", text)


def _gap(f: Forecast, target_s: float | None, vdot_needed: float | None, weeks_left: float,
         data: TrainingData, distance_m: float) -> Point | None:  # fmt: skip
    if not target_s or not f.probable_s:
        return None
    gap = f.probable_s - target_s
    if gap <= 0:
        return Point(
            "Qué te falta",
            f"Nada: tu previsión ya es {_clock(-gap)} mejor que el objetivo. Llega descansado y no salgas más rápido "
            "de lo previsto.",
        )
    text = f"Te faltan {_clock(gap)}."
    if vdot_needed and f.vdot_current:
        vdot_gap = vdot_needed - f.vdot_current
        weeks_needed = vdot_gap / VDOT_GAIN_PER_WEEK
        text += (
            f" Necesitas un VDOT de {num(vdot_needed, 1)} (tienes {num(f.vdot_current, 1)}). Una mejora realista "
            f"es de ~1 punto cada 4 semanas de entrenamiento constante, así que harían falta unas "
            f"{num(weeks_needed, 0)} semanas"
        )
        text += (
            f" y quedan {num(weeks_left, 0)}: es alcanzable." if weeks_needed <= weeks_left
            else f" y quedan {num(weeks_left, 0)}: es un objetivo ambicioso; valora ajustarlo."
        )  # fmt: skip
    long_km, weekly_km = readiness_targets(distance_m)
    levers = []
    if data.km_per_week < weekly_km:
        levers.append(f"subir progresivamente a ~{num(weekly_km, 0)} km/semana (≤ 30 % más por semana)")
    if data.longest_run_m / 1000 < long_km:
        levers.append(f"alargar la tirada larga hasta ~{num(long_km, 0)} km")
    if levers:
        text += " Lo que más te puede ayudar: " + " y ".join(levers) + "."
    return Point("Qué te falta", text)


def _calibration(f: Forecast) -> Point:
    if f.calibration_factor:
        pct = (1 - f.calibration_factor) * 100
        direction = "más rápido" if pct > 0 else "más lento"
        return Point(
            "Calibración con tus carreras",
            f"En tus carreras reales fuiste de media un {num(abs(pct), 1)} % {direction} de lo previsto, así que "
            "la previsión aplica esa corrección personal.",
        )
    return Point(
        "Calibración con tus carreras",
        "Aún no hay carreras marcadas. Cuando corras una, márcala en su objetivo: la app comparará lo que "
        "predijo con tu tiempo real y ajustará las siguientes previsiones.",
    )


def explain_forecast(
    f: Forecast,
    data: TrainingData,
    distance_m: float,
    target_s: float | None,
    vdot_needed: float | None,
    weeks_left: float,
    evolution: list[dict],
    data_then: TrainingData | None,
) -> dict:
    if f.probable_s is None:
        return {"summary": "Aún no hay datos suficientes para prever un tiempo.", "points": [], "sources": []}
    points = [
        _starting_point(f, data),
        _fatigue(f, data),
        _models(f, distance_m, data),
        _range(f, data, distance_m),
        _evolution(evolution, data_then, data, distance_m, f),
        _gap(f, target_s, vdot_needed, weeks_left, data, distance_m),
        _calibration(f),
    ]
    sources = [RIEGEL, DANIELS] + ([TANDA] if abs(distance_m - MARATHON_M) < 1000 else [])
    bases = ["tus marcas recientes", "cómo pierdes ritmo con la distancia"]
    if abs(distance_m - MARATHON_M) < 1000:
        bases.append("tu volumen de entrenamiento")
    summary = (
        f"Previsión de {_clock(f.probable_s)} para {_distance(distance_m)}, basada en "
        + ", en ".join(bases[:-1])
        + f" y en {bases[-1]}. Esto es lo que hay detrás del número:"
    )
    return {
        "summary": summary,
        "points": [asdict(p) for p in points if p],
        "sources": [asdict(s) for s in sources],
    }


# ─── Ritmos de entrenamiento ─────────────────────────────────────────────────

ZONE_PURPOSE = {
    "easy": ("E · Suave", "Base aeróbica y recuperación. Debería ser la mayor parte de tu volumen (~80 %)."),
    "marathon": ("M · Maratón", "Ritmo de competición en maratón; acostumbra al cuerpo a sostenerlo."),
    "threshold": (
        "T · Umbral",
        "Cerca del umbral láctico (un esfuerzo que aguantarías ~1 h). Tempos de 20–40 min "
        "o series de 1 km; mejora la capacidad de sostener ritmo.",
    ),  # fmt: skip
    "interval": (
        "I · Intervalos",
        "En torno a tu VO2max. Series de 3–5 min con recuperación similar; sube el techo aeróbico.",
    ),  # fmt: skip
    "repetition": (
        "R · Repeticiones",
        "Más rápido que el VO2max. Series cortas (200–400 m) con recuperación completa; mejora velocidad y economía.",
    ),  # fmt: skip
}


def explain_paces(f: Forecast) -> dict | None:
    if not f.vdot_current:
        return None
    if f.vdot_source == "marca" and f.source_distance_m and f.source_time_s and f.source_day:
        origin = (
            f"tu mejor {_distance(f.source_distance_m)} reciente ({_clock(f.source_time_s)} el {_date(f.source_day)})"
        )
    else:
        origin = "el VO2max que estima tu reloj (sin marcas recientes, menos preciso)"
    zones = [
        {
            "key": key,
            "label": ZONE_PURPOSE[key][0],
            "percent": f"{round(lo * 100)}–{round(hi * 100)} % del VDOT",
            "purpose": ZONE_PURPOSE[key][1],
        }
        for key, (lo, hi) in DANIELS_FRACTIONS.items()
    ]
    return {
        "summary": (
            f"Calculados con tu VDOT {num(f.vdot_current, 1)}, que sale de {origin}. Cada ritmo es un porcentaje de "
            "tu capacidad aeróbica según Daniels; así cada sesión entrena lo que debe y no corres todo a la misma "
            "intensidad. Se actualizan solos cuando registras mejores marcas."
        ),
        "zones": zones,
        "sources": [asdict(DANIELS), asdict(SEILER)],
    }
