"""
Avisos de riesgo de lesión por cómo se reparte la carga (orientativo, no diagnóstico):

- Subida brusca de volumen: km de los últimos 7 días frente a la media de las 3 semanas anteriores
  (> 10 % vigilar, > 30 % atención; regla del 10 %, Buist 2008; Nielsen 2014).
- Monotonía de Foster: media / desviación de la carga diaria de la semana (> 2 vigilar) y strain =
  carga semanal × monotonía (Foster 1998).
- Carga reciente frente a la habitual (ACWR EWMA > 1,5; Gabbett 2016).
- Tirada larga desproporcionada: > 40 % de los km de la semana con al menos 15 km semanales.
- Zapatillas al límite de su vida útil (600–800 km según el modelo).
"""

import statistics
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from sqlmodel import Session

from app.services import progress as prog
from app.services.es_format import num
from app.services.gear import list_gear
from app.services.insights import acwr_series
from app.services.plan_steps import local_day, sport_family

GOOD, WATCH, ALERT = "good", "watch", "alert"


@dataclass
class Check:
    key: str
    status: str
    title: str
    message: str
    evidence: list[str] = field(default_factory=list)


def volume_jump(last7_km: float, prev_weeks_km: list[float]) -> Check:
    base = statistics.fmean(prev_weeks_km) if prev_weeks_km else 0
    if base < 5:
        return Check("volume", GOOD, "Volumen estable", "Aún no hay base suficiente para comparar semanas.")
    change = (last7_km - base) / base * 100
    ev = ["Buist et al. 2008 · regla del 10 %", "Nielsen et al. 2014 · progresión del volumen"]
    if change > 30:
        return Check(
            "volume",
            ALERT,
            f"Volumen +{num(change)} % en una semana",
            f"Has corrido {num(last7_km, 1)} km en 7 días frente a {num(base, 1)} de media. Subir más de "
            "un 30 % de golpe aumenta el riesgo de lesión: la próxima semana mantén o baja.",
            ev,
        )
    if change > 10:
        return Check(
            "volume",
            WATCH,
            f"Volumen +{num(change)} % esta semana",
            "Algo por encima del 10 % recomendado. Si te notas bien, consolida antes de volver a subir.",
            ev,
        )
    if change < 0:
        return Check(
            "volume", GOOD, "Volumen a la baja", "Esta semana llevas menos kilómetros que tu media reciente.", ev
        )
    return Check(
        "volume",
        GOOD,
        "Volumen dentro de lo razonable",
        "La subida de kilómetros respecto a las semanas anteriores es gradual.",
        ev,
    )


def monotony(daily_loads: list[float]) -> Check:
    """Monotonía y strain de Foster sobre las cargas de los últimos 7 días (incluidos los de descanso)."""
    ev = ["Foster 1998 · monotonía y strain"]
    if sum(daily_loads) <= 0:
        return Check("monotony", GOOD, "Sin carga esta semana", "No hay entrenamientos en los últimos 7 días.", ev)
    sd = statistics.pstdev(daily_loads)
    mono = statistics.fmean(daily_loads) / sd if sd > 0 else 10.0
    strain = sum(daily_loads) * mono
    text = f"monotonía {num(mono, 1)}, strain {num(strain)}"
    if mono > 2:
        return Check(
            "monotony",
            WATCH,
            "Semana muy monótona",
            f"Entrenas todos los días con una carga parecida ({text}). Alterna días duros y suaves y deja "
            "algún descanso: la variedad reduce el riesgo de sobrecarga.",
            ev,
        )
    return Check("monotony", GOOD, "Buena alternancia", f"Alternas días duros y suaves ({text}).", ev)


def acwr_check(acwr: float | None) -> Check:
    ev = ["Gabbett 2016 · ratio carga aguda:crónica"]
    if acwr is None:
        return Check("acwr", GOOD, "Carga reciente", "Aún no hay 4 semanas de historial para compararla.", ev)
    text = num(acwr, 2)
    if acwr > 1.5:
        return Check(
            "acwr",
            ALERT,
            f"Pico de carga ({text})",
            "Tu carga de 7 días es más de 1,5 veces la habitual. Baja el ritmo unos días.",
            ev,
        )
    if acwr > 1.3:
        return Check(
            "acwr", WATCH, f"Carga en aumento ({text})", "Por encima de tu habitual: vigila las sensaciones.", ev
        )
    return Check("acwr", GOOD, f"Carga equilibrada ({text})", "Tu carga reciente está en línea con la habitual.", ev)


def long_run_share(longest_km: float, week_km: float) -> Check:
    if week_km < 15 or longest_km <= 0:
        return Check("long_run", GOOD, "Tirada larga", "Volumen semanal bajo: no aplica.")
    share = longest_km / week_km * 100
    if share > 40:
        return Check(
            "long_run",
            WATCH,
            f"Tirada larga = {num(share)} % de la semana",
            f"Una sola salida de {num(longest_km, 1)} km concentra demasiada carga. Reparte más los "
            "kilómetros entre los días de la semana.",
            ["Daniels · tirada larga ≤ 25–30 %"],
        )
    return Check(
        "long_run",
        GOOD,
        "Tirada larga proporcionada",
        f"Tu salida más larga es el {num(share)} % de la semana.",
        ["Daniels · tirada larga ≤ 25–30 %"],
    )


def shoes_check(shoes: list[dict]) -> Check:
    active = [s for s in shoes if not s["retired"]]
    worn = [s for s in active if s["status"] == "replace"]
    soon = [s for s in active if s["status"] == "soon"]
    ev = ["Las zapatillas pierden amortiguación entre 500 y 800 km"]
    if worn:
        names = ", ".join(f"{s['name']} ({num(s['total_km'])} km)" for s in worn)
        return Check("shoes", ALERT, "Zapatillas para cambiar", f"Han superado su límite: {names}.", ev)
    if soon:
        names = ", ".join(f"{s['name']} ({num(s['total_km'])} de {num(s['alert_km'])} km)" for s in soon)
        return Check("shoes", WATCH, "Zapatillas casi al límite", f"Ve pensando en cambiar: {names}.", ev)
    if not active:
        return Check("shoes", GOOD, "Zapatillas", "Añade tus zapatillas en Material para controlar sus kilómetros.")
    return Check("shoes", GOOD, "Zapatillas en buen estado", "Ninguna está cerca de su límite de kilómetros.", ev)


def injury_report(session: Session, user_id: int, today: date | None = None) -> dict:
    """Todas las comprobaciones con su estado y el peor como resumen."""
    today = today or date.today()
    activities = prog.user_activities(session, user_id)
    runs = [a for a in activities if sport_family(a.sport) == "running"]

    def km_between(start: date, end: date) -> float:
        return sum((a.distance_m or 0) / 1000 for a in runs if start <= local_day(a.start_time, a.timezone) < end)

    week_start = today - timedelta(days=6)
    last7 = km_between(week_start, today + timedelta(days=1))
    prev = [km_between(week_start - timedelta(days=7 * k), week_start - timedelta(days=7 * (k - 1))) for k in (1, 2, 3)]
    thresholds = prog.user_thresholds(session, user_id)
    per_day, _ = prog.loads_by_day(activities, thresholds, prog.user_rpes(session, user_id))
    daily = [per_day.get(week_start + timedelta(days=i), 0.0) for i in range(7)]
    acwr = acwr_series(per_day, today, today)
    longest = max(
        ((a.distance_m or 0) / 1000 for a in runs if local_day(a.start_time, a.timezone) >= week_start), default=0
    )
    checks = [
        volume_jump(last7, prev),
        acwr_check(acwr[-1]["acwr"] if acwr else None),
        monotony(daily),
        long_run_share(longest, last7),
        shoes_check(list_gear(session, user_id)),
    ]
    rank = {GOOD: 0, WATCH: 1, ALERT: 2}
    worst = max(checks, key=lambda c: rank[c.status])
    return {
        "status": worst.status,
        "summary": worst.title if worst.status != GOOD else "Sin señales de riesgo esta semana",
        "checks": [asdict(c) for c in checks],
        "week_km": round(last7, 1),
        "disclaimer": "Orientativo: no sustituye la valoración de un profesional sanitario.",
    }
