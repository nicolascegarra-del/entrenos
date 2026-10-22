"""
Curva de mejores ritmos por duración (1, 5, 10, 20, 30 y 60 min) y velocidad crítica.

La curva de cada actividad se calcula una vez con su serie de distancia acumulada y se
guarda en `Activity.metrics["pace_curve"]` (se recalcula si cambia `CURVE_VERSION`).
La velocidad crítica (CS) y la reserva anaeróbica (D′) salen de la regresión lineal
distancia–tiempo de las mejores marcas de 3 a 20 minutos (Monod y Scherrer, 1965;
Jones y Vanhatalo, 2017): distancia = CS · t + D′.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlmodel import Session, col, select

from app.models import Activity, ActivityStream
from app.services.plan_steps import local_day, sport_family

DURATIONS_S = (60, 300, 600, 1200, 1800, 3600)
CS_DURATIONS_S = (180, 300, 600, 1200)  # tramo «severo» donde el modelo de 2 parámetros funciona bien
CURVE_KEY = "pace_curve"
CURVE_VERSION = 2
MAX_GAP_FACTOR = 1.15  # una ventana con huecos (pausas sin registro) mayor que esto no cuenta
MIN_SPEED, MAX_SPEED = 1.0, 7.5  # m/s: descarta caminatas paradas y errores de GPS (> 2:13 /km)
# Un salto de GPS en un solo punto (cientos de metros en 1 s) falsea el mejor minuto: el avance entre dos
# muestras se limita a esta velocidad, por encima de la cual no corre nadie en una muestra aislada.
MAX_STEP_SPEED = 8.0


def best_speeds(time: list[float | None], distance: list[float | None], durations=DURATIONS_S) -> dict[int, float]:
    """
    Mejor velocidad media (m/s) sostenida durante cada duración, con dos punteros (O(n)).

    Args:
        time: segundos desde el inicio (canal `time`).
        distance: metros acumulados (canal `distance`).
        durations: duraciones en segundos.

    Returns:
        {duración: velocidad}; solo las duraciones que caben en la actividad.
    """
    raw = [(t, d) for t, d in zip(time, distance, strict=False) if t is not None and d is not None]
    out: dict[int, float] = {}
    if len(raw) < 2:
        return out
    # Distancia acumulada «limpia»: cada avance se limita a MAX_STEP_SPEED × dt (saltos de GPS).
    points = [raw[0]]
    for (t0, d0), (t1, d1) in zip(raw, raw[1:], strict=False):
        step = min(max(d1 - d0, 0.0), MAX_STEP_SPEED * max(t1 - t0, 0.0))
        points.append((t1, points[-1][1] + step))
    total = points[-1][0] - points[0][0]
    for target in durations:
        if target > total:
            continue
        best, j = 0.0, 0
        for i in range(len(points)):
            if j < i:
                j = i
            while j < len(points) - 1 and points[j][0] - points[i][0] < target:
                j += 1
            span = points[j][0] - points[i][0]
            if span < target:
                break
            if span > target * MAX_GAP_FACTOR:
                continue
            speed = (points[j][1] - points[i][1]) / span
            if speed > best and MIN_SPEED <= speed <= MAX_SPEED:
                best = speed
        if best:
            out[target] = round(best, 4)
    return out


def critical_speed(curve: dict[int, float]) -> tuple[float, float] | None:
    """
    Velocidad crítica (m/s) y D′ (m) por mínimos cuadrados de distancia = CS·t + D′.

    Returns:
        None si hay menos de 2 duraciones válidas o el ajuste no tiene sentido fisiológico.
    """
    pts = [(t, curve[t] * t) for t in CS_DURATIONS_S if t in curve]
    if len(pts) < 2:
        return None
    n = len(pts)
    mean_t = sum(t for t, _ in pts) / n
    mean_d = sum(d for _, d in pts) / n
    var = sum((t - mean_t) ** 2 for t, _ in pts)
    if var == 0:
        return None
    cs = sum((t - mean_t) * (d - mean_d) for t, d in pts) / var
    d_prime = mean_d - cs * mean_t
    if not (MIN_SPEED <= cs <= MAX_SPEED) or d_prime < 0:
        return None
    return round(cs, 4), round(d_prime, 1)


def _load_curve(session: Session, activity: Activity) -> dict[int, float]:
    """Curva guardada en la actividad o calculada ahora (y guardada) a partir de sus series."""
    cached = (activity.metrics or {}).get(CURVE_KEY)
    if cached and cached.get("v") == CURVE_VERSION:
        return {int(k): v for k, v in cached["speeds"].items()}
    streams = session.exec(
        select(ActivityStream).where(
            ActivityStream.activity_id == activity.id, col(ActivityStream.channel).in_(["time", "distance"])
        )
    ).all()
    channels = {s.channel: s.values for s in streams}
    curve = best_speeds(channels.get("time", []), channels.get("distance", []))
    activity.metrics = {**(activity.metrics or {}), CURVE_KEY: {"v": CURVE_VERSION, "speeds": curve}}
    session.add(activity)
    return curve


@dataclass
class Best:
    speed: float
    activity_id: int
    day: date


def best_curve(session: Session, activities: list[Activity], since: date, until: date) -> dict[int, Best]:
    """Mejor marca por duración entre las carreras del periodo [since, until]."""
    best: dict[int, Best] = {}
    for a in activities:
        day = local_day(a.start_time, a.timezone)
        if not (since <= day <= until) or sport_family(a.sport) != "running":
            continue
        for duration, speed in _load_curve(session, a).items():
            if duration not in best or speed > best[duration].speed:
                best[duration] = Best(speed, a.id, day)
    return best


def pace_s_km(speed: float) -> float:
    return round(1000 / speed, 1)


def build_pace_curve(session: Session, activities: list[Activity], days: int, today: date | None = None) -> dict:
    """
    Curva del periodo, la del periodo anterior de la misma longitud (para comparar), su evolución por
    trimestres (último año) y la velocidad crítica del periodo.
    """
    today = today or date.today()
    since = today - timedelta(days=days)
    current = best_curve(session, activities, since, today)
    previous = best_curve(session, activities, since - timedelta(days=days), since - timedelta(days=1))
    quarters = []
    for q in range(3, -1, -1):
        end = today - timedelta(days=91 * q)
        start = end - timedelta(days=90)
        curve = best_curve(session, activities, start, end)
        quarters.append({
            "label": f"{start.strftime('%m/%Y')}–{end.strftime('%m/%Y')}",
            "paces": {str(d): pace_s_km(b.speed) for d, b in curve.items()},
        })  # fmt: skip
    session.commit()  # guarda las curvas calculadas por primera vez
    cs = critical_speed({d: b.speed for d, b in current.items()})
    return {
        "durations": [
            {
                "seconds": d,
                "best": _best_out(current.get(d)),
                "previous": _best_out(previous.get(d)),
            }
            for d in DURATIONS_S
        ],
        "quarters": quarters,
        "critical_speed": ({"speed": cs[0], "pace_s_km": pace_s_km(cs[0]), "d_prime_m": cs[1]} if cs else None),
    }


def _best_out(b: Best | None) -> dict | None:
    if b is None:
        return None
    return {"pace_s_km": pace_s_km(b.speed), "speed": b.speed, "activity_id": b.activity_id, "day": b.day.isoformat()}
