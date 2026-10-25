"""
Plan del día de carrera: ajuste por calor y por desnivel, ritmo por km y avituallamiento.

- Calor: regla de temperatura + punto de rocío (°F): por encima de 100 el ritmo empeora de forma
  creciente (0,5 % a 110, 2 % a 130, 4,5 % a 150, 8 % a 170…). Coherente con Ely et al. 2007 (el
  rendimiento en maratón cae al subir la temperatura por encima de ~10 °C).
- Desnivel: regla empírica de Daniels (12–15 s/milla por cada 1 % de subida ≈ +3 % de tiempo) y en
  bajada se recupera ~55 % de lo que cuesta subir, hasta −10 % (más empinado ya no ayuda: se frena).
  El coste metabólico de Minetti et al. 2002 exagera el efecto en el ritmo con pendientes suaves.
- Sin GPX, con el desnivel positivo total se supone un recorrido de subidas y bajadas iguales.
- Avituallamiento (vía `services.nutrition`): enjuague entre 45 y 75 min, hidratos 30–60 g/h hasta 2,5 h
  y 60–90 g/h en pruebas más largas (Jeukendrup 2014); líquido 400–800 ml/h según el calor (ACSM 2007);
  sodio si dura > 2 h o hace calor.
"""

import math
import re
import xml.etree.ElementTree as ET  # noqa: N817

from app.services import nutrition
from app.services.routes import haversine

UPHILL_PER_GRADE = 3.0  # +3 % de tiempo por cada 1 % de pendiente
DOWNHILL_SHARE = 0.55
MAX_DOWNHILL = 0.10
GEL_CARBS_G = nutrition.GEL_CARBS_G
MAX_GPX_BYTES = 5_000_000
PROFILE_POINTS = 400
TRACK_POINTS = 300

# Temperatura + punto de rocío en °F → empeoramiento del ritmo en %.
HEAT_KNOTS = [(100, 0.0), (110, 0.5), (120, 1.0), (130, 2.0), (140, 3.0), (150, 4.5), (160, 6.0), (170, 8.0),
              (180, 10.0)]  # fmt: skip


class GpxError(ValueError):
    """El fichero no es un GPX válido o no tiene puntos."""


# ─── GPX ─────────────────────────────────────────────────────────────────────


def _smooth(values: list[float], window: int = 5) -> list[float]:
    half = window // 2
    return [sum(values[max(0, i - half) : i + half + 1]) / len(values[max(0, i - half) : i + half + 1])
            for i in range(len(values))]  # fmt: skip


def parse_gpx(text: str, name: str = "") -> dict:
    """
    Perfil del recorrido desde un GPX (track o ruta): distancia, desnivel y ~400 puntos para la gráfica.

    Raises:
        GpxError: si no es GPX, trae entidades XML (se rechazan por seguridad) o no tiene altitudes.
    """
    if len(text.encode()) > MAX_GPX_BYTES:
        raise GpxError("El GPX es demasiado grande (máximo 5 MB).")
    if re.search(r"<!(DOCTYPE|ENTITY)", text, re.IGNORECASE):
        raise GpxError("El GPX no puede incluir declaraciones DOCTYPE ni ENTITY.")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise GpxError("No es un fichero GPX válido.") from exc
    pts: list[tuple[float, float, float | None]] = []
    for el in root.iter():
        if el.tag.split("}")[-1] in ("trkpt", "rtept"):
            try:
                lat, lon = float(el.attrib["lat"]), float(el.attrib["lon"])
            except (KeyError, ValueError):
                continue
            ele_el = next((c for c in el if c.tag.split("}")[-1] == "ele"), None)
            ele = float(ele_el.text) if ele_el is not None and ele_el.text else None
            pts.append((lat, lon, ele))
    if len(pts) < 2:
        raise GpxError("El GPX no tiene puntos de recorrido.")
    if sum(p[2] is not None for p in pts) < len(pts) * 0.8:
        raise GpxError("El GPX no trae altitudes: sin ellas no se puede calcular el desnivel.")
    dist = [0.0]
    for p, q in zip(pts, pts[1:], strict=False):
        dist.append(dist[-1] + haversine(p[:2], q[:2]))
    last = next(p[2] for p in pts if p[2] is not None)
    raw = []
    for p in pts:
        last = p[2] if p[2] is not None else last
        raw.append(last)
    ele = _smooth(raw)
    gain = sum(max(0.0, b - a) for a, b in zip(ele, ele[1:], strict=False))
    loss = sum(max(0.0, a - b) for a, b in zip(ele, ele[1:], strict=False))
    step = max(1, len(pts) // PROFILE_POINTS)
    tstep = max(1, len(pts) // TRACK_POINTS)
    return {
        "name": name[:120],
        "distance_m": round(dist[-1]),
        "gain_m": round(gain),
        "loss_m": round(loss),
        "points": [[round(dist[i]), round(ele[i], 1)] for i in range(0, len(pts), step)] + [[round(dist[-1]),
                                                                                                round(ele[-1], 1)]],
        "track": [[round(p[0], 6), round(p[1], 6)] for p in pts[::tstep]],
        "start": [round(pts[0][0], 5), round(pts[0][1], 5)],
    }  # fmt: skip


# ─── Desnivel ────────────────────────────────────────────────────────────────


def grade_factor(grade: float) -> float:
    """Cuánto más (o menos) tiempo cuesta un tramo frente al llano (pendiente en tanto por uno)."""
    if grade >= 0:
        return 1 + UPHILL_PER_GRADE * grade
    return 1 - UPHILL_PER_GRADE * DOWNHILL_SHARE * min(-grade, MAX_DOWNHILL)


def km_factors(points: list[list[float]], distance_m: float) -> list[float]:
    """Factor de tiempo de cada km del perfil (tramos de ~100 m), escalado a la distancia de la carrera."""
    if len(points) < 2:
        return [1.0] * max(1, math.ceil(distance_m / 1000))
    scale = distance_m / points[-1][0] if points[-1][0] else 1.0
    n_km = max(1, math.ceil(distance_m / 1000))
    acc = [[0.0, 0.0] for _ in range(n_km)]  # [metros, metros × factor]
    for (d0, e0), (d1, e1) in zip(points, points[1:], strict=False):
        length = (d1 - d0) * scale
        if length <= 0:
            continue
        f = grade_factor((e1 - e0) / (d1 - d0))
        k = min(n_km - 1, int((d0 * scale) // 1000))
        acc[k][0] += length
        acc[k][1] += length * f
    return [round(b / a, 4) if a else 1.0 for a, b in acc]


def gain_factor(distance_m: float, gain_m: float) -> float:
    """Sin GPX: mitad del recorrido subiendo `gain_m` y la otra mitad bajándolo."""
    if not gain_m or distance_m <= 0:
        return 1.0
    g = gain_m / (distance_m / 2)
    return (grade_factor(g) + grade_factor(-g)) / 2


# ─── Calor ───────────────────────────────────────────────────────────────────


def c_to_f(c: float) -> float:
    return c * 9 / 5 + 32


def heat_slowdown_pct(temp_c: float, dew_point_c: float) -> float:
    """Empeoramiento del ritmo (%) por calor y humedad (temperatura + punto de rocío en °F)."""
    s = c_to_f(temp_c) + c_to_f(dew_point_c)
    if s <= HEAT_KNOTS[0][0]:
        return 0.0
    for (x0, y0), (x1, y1) in zip(HEAT_KNOTS, HEAT_KNOTS[1:], strict=False):
        if s <= x1:
            return round(y0 + (y1 - y0) * (s - x0) / (x1 - x0), 2)
    return 12.0


def heat_level(pct: float, sum_f: float) -> tuple[str, str]:
    if sum_f > 180:
        return "alert", "Calor extremo: no es un día para buscar marca. Corre por sensaciones e hidrátate mucho."
    if pct >= 3:
        return "alert", "Mucho calor para correr rápido: sal más conservador y bebe desde el principio."
    if pct > 0.5:
        return "watch", "Algo de calor y humedad: ajusta el ritmo y no te saltes avituallamientos."
    return "good", "Condiciones buenas para correr rápido."


# ─── Plan de ritmos y avituallamiento ────────────────────────────────────────


def pacing_plan(total_s: float, distance_m: float, factors: list[float]) -> list[dict]:
    """
    Ritmo por km con el mismo esfuerzo: cada km recibe tiempo proporcional a su factor de desnivel,
    repartiendo `total_s` exactamente (el último km puede ser parcial).
    """
    n = len(factors)
    lengths = [min(1000.0, distance_m - 1000 * k) for k in range(n)]
    weights = [f * length for f, length in zip(factors, lengths, strict=False)]
    unit = total_s / sum(weights)
    out, cum = [], 0.0
    for k, (f, length) in enumerate(zip(factors, lengths, strict=False)):
        seg = f * length * unit
        cum += seg
        out.append({"km": k + 1, "distance_m": round(length), "factor": f, "time_s": round(seg, 1),
                    "pace_s_km": round(seg / length * 1000, 1), "cum_s": round(cum)})  # fmt: skip
    return out


def fueling(duration_s: float, temp_c: float | None) -> dict:
    """
    Hidratos, geles, líquido y sodio recomendados según la duración y la temperatura.

    Las bandas de hidratos y de líquido salen de `services.nutrition` (Jeukendrup 2014, ACSM 2007) para que
    el día de carrera y el módulo de nutrición den las mismas cifras.
    """
    hours = duration_s / 3600
    band = nutrition.carbs_band(duration_s / 60)
    carbs, note = (band.low, band.high), band.note
    t = temp_c if temp_c is not None else 15
    fluid = nutrition.fluid_ml_h(temp_c)
    # Geles para cubrir el mínimo recomendado desde la primera toma (el resto, con bebida isotónica).
    first_gel_min = 30 if band.key == "hasta-90" else 40
    fuel_hours = max(0.0, duration_s / 60 - first_gel_min) / 60
    gels = max(1, round(carbs[0] * fuel_hours / GEL_CARBS_G)) if carbs[0] else 0
    interval = max(15, round(fuel_hours * 60 / gels)) if gels else None
    return {
        "carbs_g_h": list(carbs),
        "gels": gels,
        "gel_times_min": [first_gel_min + i * interval for i in range(gels)] if interval else [],
        "fluid_ml_h": list(fluid),
        "sodium": hours > 2 or t >= 25,
        "note": note,
        "evidence": ["Jeukendrup 2014 · hidratos en carrera", "ACSM 2007 · hidratación en el ejercicio"],
    }


# ─── Informe del día de carrera ──────────────────────────────────────────────


def _course_factors(goal) -> tuple[list[float], dict | None]:
    """Factores por km y resumen del desnivel (GPX, D+ escrito a mano o llano)."""
    n_km = max(1, math.ceil(goal.distance_m / 1000))
    if goal.course and goal.course.get("points"):
        c = goal.course
        return km_factors(c["points"], goal.distance_m), {
            "source": "gpx", "name": c.get("name", ""), "gain_m": c["gain_m"], "loss_m": c["loss_m"],
            "distance_m": c["distance_m"], "profile": c["points"], "track": c.get("track", []),
        }  # fmt: skip
    if goal.elevation_gain_m:
        f = round(gain_factor(goal.distance_m, goal.elevation_gain_m), 4)
        return [f] * n_km, {"source": "gain", "gain_m": goal.elevation_gain_m, "loss_m": goal.elevation_gain_m}
    return [1.0] * n_km, None


def report(session, goal, today=None) -> dict:
    """Previsión ajustada por clima y desnivel, ritmo por km (previsto y objetivo) y avituallamiento."""
    from app.services.race_forecast import goal_forecast  # import local: evita un ciclo de imports
    from app.services.weather import WeatherError, cached_weather

    f = goal_forecast(session, goal)
    base_s = f.probable_s or goal.target_time_s
    if not base_s:
        return {"available": False, "reason": "Necesitamos una previsión o un tiempo objetivo para planificar."}
    weather, weather_error = None, None
    try:
        weather = cached_weather(goal, math.ceil(base_s / 3600), today)
        session.add(goal)
        session.commit()
    except WeatherError as exc:
        weather_error = str(exc)
    heat = None
    if weather and weather.get("temp_c") is not None and weather.get("dew_point_c") is not None:
        pct = heat_slowdown_pct(weather["temp_c"], weather["dew_point_c"])
        level, advice = heat_level(pct, c_to_f(weather["temp_c"]) + c_to_f(weather["dew_point_c"]))
        heat = {"pct": pct, "status": level, "advice": advice,
                "evidence": ["Regla temperatura + punto de rocío", "Ely et al. 2007 · calor y maratón"]}  # fmt: skip
    factors, course = _course_factors(goal)
    lengths = [min(1000.0, goal.distance_m - 1000 * k) for k in range(len(factors))]
    elev_factor = sum(fa * le for fa, le in zip(factors, lengths, strict=False)) / goal.distance_m
    adjusted_s = base_s * elev_factor * (1 + (heat["pct"] if heat else 0) / 100)
    return {
        "available": True,
        "base_s": round(base_s),
        "base_source": "forecast" if f.probable_s else "target",
        "elevation_pct": round((elev_factor - 1) * 100, 1),
        "heat_pct": heat["pct"] if heat else 0,
        "adjusted_s": round(adjusted_s),
        "target_s": goal.target_time_s,
        "weather": weather,
        "weather_error": weather_error,
        "heat": heat,
        "course": course,
        "pacing": pacing_plan(adjusted_s, goal.distance_m, factors),
        "pacing_target": pacing_plan(goal.target_time_s, goal.distance_m, factors) if goal.target_time_s else None,
        "fueling": fueling(adjusted_s, weather.get("temp_c") if weather else None),
        "elevation_evidence": ["Daniels · 12–15 s/milla por cada 1 % de subida", "Minetti et al. 2002"],
    }
