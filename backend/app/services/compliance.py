"""
Plan vs real: alinea los pasos planificados con lo que registró el reloj y puntúa
el cumplimiento de cada paso.

Funciones puras: reciben vueltas (dicts como `Lap`) y canales de streams.
"""

import math
from dataclasses import dataclass, field

from app.services.plan_steps import Step

# Coste de dejar una vuelta fuera del plan (ej. un lap pulsado sin querer o unas
# aceleraciones no planificadas). Más alto que un desajuste moderado de distancia.
SKIP_COST = 0.8
SKIP_COST_TINY = 0.05  # vueltas de < 20 s o < 30 m: casi gratis ignorarlas
OPEN_STEP_COST = 0.3  # pasos sin duración ni distancia ("libre")
MAX_LAPS_PER_STEP = 10  # acota el alineamiento a O(pasos × vueltas × 10)
# Peso de la diferencia de ritmo en pasos con objetivo: evita que una serie absorba un
# descanso andando (ej. la transición entre bloques) en vez de dejarlo fuera del plan.
PACE_WEIGHT = 1.0
# Penalización de puntuación por cada 1 % fuera del rango objetivo.
SCORE_PER_PCT = 5.0
OK_SCORE, NEAR_SCORE = 90.0, 70.0


@dataclass
class Segment:
    """Tramo real (una o varias vueltas, o un trozo del stream) asignado a un paso."""

    duration_s: float = 0.0
    distance_m: float = 0.0
    hr: float | None = None
    power: float | None = None
    cadence: float | None = None
    laps: list[int] = field(default_factory=list)

    @property
    def speed(self) -> float | None:
        return self.distance_m / self.duration_s if self.duration_s > 0 and self.distance_m > 0 else None


def _weighted(pairs: list[tuple[float | None, float]]) -> float | None:
    valid = [(v, w) for v, w in pairs if v is not None and w > 0]
    total = sum(w for _, w in valid)
    return sum(v * w for v, w in valid) / total if total else None


def merge_laps(laps: list[dict]) -> Segment:
    return Segment(
        duration_s=sum(lap["duration_s"] or 0 for lap in laps),
        distance_m=sum(lap["distance_m"] or 0 for lap in laps),
        hr=_weighted([(lap["avg_hr"], lap["duration_s"]) for lap in laps]),
        power=_weighted([(lap["metrics"].get("avg_power"), lap["duration_s"]) for lap in laps]),
        cadence=_weighted([(lap["metrics"].get("avg_cadence"), lap["duration_s"]) for lap in laps]),
        laps=[lap["index"] for lap in laps],
    )


def metric_value(metric: str, segment: Segment) -> float | None:
    speed = segment.speed
    match metric:
        case "pace":
            return 1000 / speed if speed and speed > 0.3 else None
        case "speed":
            return speed * 3.6 if speed else None
        case "hr":
            return segment.hr
        case "power":
            return segment.power
        case "cadence":
            return segment.cadence
    return None


def _target_speed(step: Step) -> float | None:
    """Velocidad objetivo (m/s) del paso, para ayudar a distinguir series de recuperaciones."""
    if step.target_metric not in ("pace", "speed"):
        return None
    values = [v for v in (step.target_min, step.target_max) if v]
    if not values:
        return None
    mid = sum(values) / len(values)
    return 1000 / mid if step.target_metric == "pace" else mid / 3.6


def _step_cost(step: Step, segment: Segment) -> float:
    if step.distance_m:
        cost = abs(math.log(max(segment.distance_m, 1) / step.distance_m))
    elif step.duration_s:
        cost = abs(math.log(max(segment.duration_s, 1) / step.duration_s))
    else:
        cost = OPEN_STEP_COST
    target = _target_speed(step)
    if target and segment.speed:
        cost += PACE_WEIGHT * abs(math.log(segment.speed / target))
    return cost


def _skip_cost(lap: dict) -> float:
    tiny = (lap["duration_s"] or 0) < 20 or (lap["distance_m"] or 0) < 30
    return SKIP_COST_TINY if tiny else SKIP_COST


def align_laps(steps: list[Step], laps: list[dict]) -> tuple[list[Segment], list[int]]:
    """
    Alineamiento óptimo (programación dinámica) de pasos con grupos de vueltas consecutivas.

    Cada paso recibe ≥1 vueltas seguidas; una vuelta puede quedar fuera del plan pagando
    `SKIP_COST`. Minimiza la diferencia relativa entre lo planificado (distancia o
    duración) y lo real, más la diferencia de velocidad si el paso tiene objetivo de ritmo.

    Returns:
        (segmento por paso, índices de vueltas no planificadas).
    """
    n, m = len(steps), len(laps)
    inf = float("inf")
    # cost[i][j]: mejor coste asignando los i primeros pasos usando las j primeras vueltas.
    cost = [[inf] * (m + 1) for _ in range(n + 1)]
    back: list[list[tuple[str, int] | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    cost[0][0] = 0.0
    for j in range(1, m + 1):
        cost[0][j] = cost[0][j - 1] + _skip_cost(laps[j - 1])
        back[0][j] = ("skip", j - 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            best, choice = cost[i][j - 1] + _skip_cost(laps[j - 1]), ("skip", j - 1)
            for k in range(j - 1, max(j - 1 - MAX_LAPS_PER_STEP, -1), -1):
                if cost[i - 1][k] == inf:
                    continue
                candidate = cost[i - 1][k] + _step_cost(steps[i - 1], merge_laps(laps[k:j]))
                if candidate < best:
                    best, choice = candidate, ("take", k)
            cost[i][j], back[i][j] = best, choice

    segments: list[Segment] = [Segment() for _ in steps]
    skipped: list[int] = []
    i, j = n, m
    while j > 0:
        move = back[i][j]
        if move is None:  # quedan pasos sin vueltas (más pasos que vueltas)
            break
        if move[0] == "skip":
            skipped.append(laps[j - 1]["index"])
            j -= 1
        else:
            segments[i - 1] = merge_laps(laps[move[1] : j])
            i, j = i - 1, move[1]
    return segments, sorted(skipped)


def split_streams(steps: list[Step], channels: dict[str, list[float | None]]) -> list[Segment]:
    """Sin vueltas útiles: recorre el stream en orden consumiendo la distancia/tiempo de cada paso."""
    time = channels.get("time") or []
    distance = channels.get("distance") or []
    n = len(time)
    segments: list[Segment] = []
    start = 0
    for position, step in enumerate(steps):
        end = start
        if step.distance_m and distance:
            base = distance[start] or 0
            while end < n - 1 and (distance[end] or 0) - base < step.distance_m:
                end += 1
        elif step.duration_s and time:
            base = time[start] or 0
            while end < n - 1 and (time[end] or 0) - base < step.duration_s:
                end += 1
        elif position == len(steps) - 1:
            end = n - 1  # paso libre final: el resto de la actividad
        sl = slice(start, end + 1)

        def mean(name: str, s: slice = sl) -> float | None:
            values = [v for v in (channels.get(name) or [])[s] if v is not None]
            return sum(values) / len(values) if values else None

        segments.append(
            Segment(
                duration_s=((time[end] or 0) - (time[start] or 0)) if time else 0.0,
                distance_m=((distance[end] or 0) - (distance[start] or 0)) if distance else 0.0,
                hr=mean("hr"),
                power=mean("power"),
                cadence=mean("cadence"),
            )
        )
        start = end
    return segments


def _completion(step: Step, segment: Segment) -> float | None:
    if step.distance_m:
        return segment.distance_m / step.distance_m
    if step.duration_s:
        return segment.duration_s / step.duration_s
    return None


def _status(score: float) -> str:
    return "ok" if score >= OK_SCORE else "near" if score >= NEAR_SCORE else "off"


def score_step(step: Step, segment: Segment) -> dict:
    """Puntúa un paso: 100 dentro del rango, −5 por cada 1 % fuera; penaliza no completarlo."""
    completion = _completion(step, segment)
    result: dict = {
        "label": step.label,
        "kind": step.kind,
        "planned": {
            "duration_s": step.duration_s,
            "distance_m": step.distance_m,
            "target_metric": step.target_metric,
            "target_min": step.target_min,
            "target_max": step.target_max,
        },
        "actual": {
            "duration_s": round(segment.duration_s, 1),
            "distance_m": round(segment.distance_m, 1),
            "laps": segment.laps,
            "value": None,
        },
        "completion": round(completion, 3) if completion is not None else None,
        "score": None,
        "status": None,
        "direction": None,
    }
    if not step.has_target:
        if completion is not None:
            result["status"] = "ok" if 0.9 <= completion <= 1.15 else "near" if 0.75 <= completion <= 1.3 else "off"
        return result

    value = metric_value(step.target_metric, segment)
    result["actual"]["value"] = round(value, 1) if value is not None else None
    if value is None:
        result["status"] = "off"
        result["score"] = 0.0
        return result

    lo, hi = step.target_min, step.target_max
    mid = sum(v for v in (lo, hi) if v is not None) / len([v for v in (lo, hi) if v is not None])
    deviation = 0.0
    if lo is not None and value < lo:
        deviation = (lo - value) / mid
        result["direction"] = "fast" if step.target_metric == "pace" else "low"
    elif hi is not None and value > hi:
        deviation = (value - hi) / mid
        result["direction"] = "slow" if step.target_metric == "pace" else "high"
    score = max(0.0, 100.0 - deviation * 100 * SCORE_PER_PCT)
    if completion is not None and completion < 0.9:
        score *= max(completion, 0.0)
    result["score"] = round(score, 1)
    result["status"] = _status(score)
    return result


def compute_compliance(steps: list[Step], laps: list[dict], channels: dict[str, list[float | None]]) -> dict:
    """
    Calcula el cumplimiento de la sesión.

    Usa las vueltas si hay al menos dos (el atleta marcó laps); si no, divide el stream.
    La nota global es la media de los pasos con objetivo ponderada por su duración real;
    si ningún paso tiene objetivo, es el porcentaje de volumen completado.
    """
    if not steps:
        return {"score": None, "method": None, "steps": [], "unplanned_laps": []}
    if len(laps) >= 2:
        segments, unplanned = align_laps(steps, laps)
        method = "laps"
    else:
        segments, unplanned = split_streams(steps, channels), []
        method = "streams"

    results = [score_step(step, seg) for step, seg in zip(steps, segments, strict=True)]
    scored = [(r["score"], r["actual"]["duration_s"] or 1) for r in results if r["score"] is not None]
    if scored:
        total = sum(w for _, w in scored)
        score = sum(s * w for s, w in scored) / total
    else:
        ratios = [r["completion"] for r in results if r["completion"] is not None]
        score = min(100.0, 100 * sum(ratios) / len(ratios)) if ratios else None
    return {
        "score": round(score, 1) if score is not None else None,
        "method": method,
        "steps": results,
        "unplanned_laps": unplanned,
    }
