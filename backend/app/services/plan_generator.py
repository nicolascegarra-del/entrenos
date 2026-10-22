"""
Generador de planes de entrenamiento hacia un objetivo de carrera (funciones puras).

Principios (literatura de entrenamiento de fondo):
- Periodización base → construcción → pico → afinamiento (Bompa; Daniels' Running Formula).
- Subida de volumen ≤ 10 % por semana y semana de descarga (−25 %) cada 4 (regla del 10 %, Buist 2008;
  ciclos 3:1).
- ~80 % del tiempo suave y ~20 % de calidad (Seiler 2010): como mucho 2 sesiones de calidad por semana.
- Tirada larga ≈ 25–30 % del volumen semanal, con tope según la distancia objetivo.
- Ritmos de Daniels a partir del VDOT actual (E, M, T, I) y ritmo de carrera del objetivo.
- Afinamiento de 1 semana (≤ 10 km) o 2 (media y maratón): −30 % y semana de carrera −50 % (Mujika 2003).
"""

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

MIN_WEEKS, MAX_WEEKS = 4, 24
RECOVERY_EVERY = 4
RECOVERY_FACTOR = 0.75
MAX_WEEKLY_INCREASE = 0.10

PHASE_LABEL = {"base": "Base", "build": "Construcción", "peak": "Pico", "taper": "Afinamiento"}

KIND_LABEL = {
    "easy": "Rodaje suave",
    "long": "Tirada larga",
    "threshold": "Umbral",
    "intervals": "Series",
    "race_pace": "Ritmo de carrera",
    "race": "Carrera",
}


@dataclass(frozen=True)
class PlanInput:
    race_date: date
    distance_m: float
    start: date  # lunes de la primera semana
    weekdays: tuple[int, ...]  # días de entrenamiento (0 = lunes)
    long_run_weekday: int
    current_km_week: float  # media de las últimas 4 semanas
    paces: dict[str, tuple[int, int]]  # Daniels (s/km, rápido-lento): easy, marathon, threshold, interval
    race_pace_s_km: float
    max_sessions_week: int | None = None  # cuentas Básicas


@dataclass
class Block:
    kind: str  # warmup | steady | interval | recovery | cooldown
    distance_m: float | None = None
    duration_s: float | None = None
    repeat: int = 1
    pace: tuple[float, float] | None = None
    recovery_duration_s: float | None = None


@dataclass
class Workout:
    day: date
    kind: str
    title: str
    km: float
    notes: str
    blocks: list[Block] = field(default_factory=list)


@dataclass
class Week:
    index: int
    start: date
    phase: str
    target_km: float
    is_recovery: bool
    workouts: list[Workout] = field(default_factory=list)


def taper_weeks(distance_m: float) -> int:
    return 1 if distance_m <= 10_000 else 2


def peak_km(distance_m: float, current_km: float) -> float:
    """Volumen semanal de pico razonable para la distancia (sin pasar de ×1,6 el actual)."""
    by_distance = 25 if distance_m <= 5_000 else 35 if distance_m <= 10_000 else 45 if distance_m <= 21_100 else 60
    return min(max(by_distance, current_km), max(current_km, 10) * 1.6)


def long_run_cap_km(distance_m: float) -> float:
    return 10 if distance_m <= 5_000 else 15 if distance_m <= 10_000 else 21 if distance_m <= 21_100 else 32


def phases(total_weeks: int, distance_m: float) -> list[str]:
    """Fase de cada semana: base (~40 %), construcción (~60 %), 2 de pico y el afinamiento final."""
    taper = taper_weeks(distance_m)
    peak = 2 if total_weeks >= 8 else 1
    rest = max(total_weeks - taper - peak, 1)
    base = max(1, round(rest * 0.4))
    build = max(rest - base, 0)
    out = ["base"] * base + ["build"] * build + ["peak"] * peak + ["taper"] * taper
    return out[-total_weeks:] if len(out) > total_weeks else out


def weekly_volumes(n_phases: list[str], start_km: float, top_km: float) -> list[tuple[float, bool]]:
    """
    Kilómetros objetivo por semana y si es de descarga. Sube como mucho un 10 % por semana hasta el pico,
    con descarga cada 4 semanas, y baja en el afinamiento (−30 %, semana de carrera −50 %).
    """
    out: list[tuple[float, bool]] = []
    km = max(start_km, 8.0)
    top_reached = km
    taper_left = n_phases.count("taper")
    for i, phase in enumerate(n_phases):
        if phase == "taper":
            factor = 0.5 if taper_left == 1 else 0.7
            taper_left -= 1
            out.append((round(top_reached * factor, 1), False))
            continue
        recovery = (i + 1) % RECOVERY_EVERY == 0 and phase != "peak"
        if not recovery and i > 0:
            km = min(km * (1 + MAX_WEEKLY_INCREASE), top_km)
        top_reached = km
        out.append((round(km * RECOVERY_FACTOR if recovery else km, 1), recovery))
    return out


def _quality_kinds(phase: str, sessions: int, recovery: bool) -> list[str]:
    """Sesiones de calidad de la semana (≤ 2, el resto suaves: ~80/20)."""
    if recovery or sessions <= 2:
        return [] if recovery or sessions < 2 else ["threshold"] if phase != "base" else []
    if phase == "base":
        return ["threshold"]
    if phase == "build":
        return ["threshold", "intervals"] if sessions >= 4 else ["threshold"]
    if phase == "peak":
        return ["intervals", "race_pace"] if sessions >= 4 else ["race_pace"]
    return ["race_pace"]  # taper


def _round_km(km: float) -> float:
    return max(3.0, round(km * 2) / 2)


WARM_KM, COOL_KM = 1.5, 1.0  # calentamiento y vuelta a la calma de las sesiones de calidad


def _reps(work_km: float, rep_km: float, low: int, high: int) -> int:
    """Repeticiones que caben en `work_km` (hacia abajo: la sesión no se pasa de su presupuesto)."""
    return max(low, min(high, math.floor(work_km / rep_km + 1e-9)))


def build_workout(kind: str, day: date, km: float, inp: PlanInput, phase: str) -> Workout:
    """
    Sesión con bloques y ritmos (s/km) del VDOT; los rangos van de rápido a lento.
    `km` es lo que le toca a la sesión: las series se dimensionan para encajar en ese presupuesto
    (repeticiones más cortas con poco volumen, más largas con mucho).
    """
    e, t, i = inp.paces["easy"], inp.paces["threshold"], inp.paces["interval"]
    rp = (round(inp.race_pace_s_km - 5), round(inp.race_pace_s_km + 5))
    warm = Block("warmup", distance_m=WARM_KM * 1000, pace=e)
    cool = Block("cooldown", distance_m=COOL_KM * 1000, pace=e)
    work = max(km - WARM_KM - COOL_KM, 1.6)
    if kind in ("easy", "long"):
        blocks = [Block("steady", distance_m=km * 1000, pace=e)]
        notes = "Ritmo conversacional: deberías poder hablar. Si el pulso sube a Z3, baja el ritmo."
    elif kind == "threshold":
        rep = 1.6 if work >= 6 else 1.0
        reps = _reps(work, rep, 2, 6)
        blocks = [warm, Block("interval", distance_m=rep * 1000, repeat=reps, pace=t, recovery_duration_s=60), cool]
        km = WARM_KM + COOL_KM + reps * rep
        notes = "Ritmo «cómodamente duro»: podrías decir frases cortas. Recuperación trotando."
    elif kind == "intervals":
        rep = 1.0 if work >= 5 else 0.8 if work >= 3 else 0.4
        reps = _reps(work, rep, 3, 10)
        blocks = [warm, Block("interval", distance_m=rep * 1000, repeat=reps, pace=i,
                              recovery_duration_s=round(rep * 150)), cool]  # fmt: skip
        km = WARM_KM + COOL_KM + reps * rep
        notes = "Series a ritmo de VO2max: duras pero iguales todas. Recupera trotando suave."
    elif kind == "race_pace":
        share = 0.5 if phase == "taper" else 0.75
        steady = round(max(1.0, min(work, inp.distance_m / 1000 * share)) * 2) / 2
        blocks = [warm, Block("steady", distance_m=steady * 1000, pace=rp), cool]
        km = WARM_KM + COOL_KM + steady
        notes = "Ensaya el ritmo objetivo de la carrera, con el material que llevarás ese día."
    else:  # race
        blocks = [Block("steady", distance_m=inp.distance_m, pace=rp)]
        km = inp.distance_m / 1000
        notes = "¡Día de carrera! Sal a tu ritmo objetivo y no te dejes llevar los primeros kilómetros."
    return Workout(day=day, kind=kind, title=KIND_LABEL[kind], km=round(km, 1), notes=notes, blocks=blocks)


def long_run_km(week_km: float, sessions: int, distance_m: float) -> float:
    """
    Tirada larga: ~30 % de la semana, pero siempre la sesión más larga (al menos 1,5 km más que el
    reparto igual del resto) y con tope según la distancia objetivo.
    """
    others = max(sessions - 1, 1)
    longest_needed = (week_km / others + 1.5) / (1 + 1 / others)
    return _round_km(min(max(week_km * 0.3, longest_needed), long_run_cap_km(distance_m)))


def week_workouts(week: Week, inp: PlanInput) -> list[Workout]:
    """Reparte el volumen de la semana en los días disponibles (tirada larga + calidad + suaves)."""
    end = week.start + timedelta(days=7)
    days = sorted(d for d in (week.start + timedelta(days=w) for w in inp.weekdays) if d < end)
    if inp.max_sessions_week:
        days = days[: inp.max_sessions_week]
    race_day = inp.race_date if week.start <= inp.race_date < end else None
    if race_day:
        days = [d for d in days if d < race_day - timedelta(days=1)][-2:] + [race_day]
    if not days:
        return []
    long_day = next((d for d in days if d.weekday() == inp.long_run_weekday and d != race_day), None)
    if long_day is None and len(days) >= 3 and not race_day:
        long_day = days[-1]
    quality = _quality_kinds(week.phase, len(days), week.is_recovery) if not race_day else ["race_pace"]
    workouts: list[Workout] = []
    remaining = week.target_km
    if race_day:
        workouts.append(build_workout("race", race_day, 0, inp, week.phase))
        remaining = max(remaining - inp.distance_m / 1000, 3)
    long_km = 0.0
    if long_day:
        long_km = long_run_km(week.target_km, len(days), inp.distance_m)
        workouts.append(build_workout("long", long_day, long_km, inp, week.phase))
        remaining -= long_km
    free = [d for d in days if d not in (long_day, race_day)]
    # Calidad separada de la tirada larga (no en días consecutivos cuando se puede).
    free_for_quality = sorted(free, key=lambda d: -min(abs((d - long_day).days) if long_day else 7, 7))
    q_days = sorted(free_for_quality[: len(quality)])
    share = remaining / max(len(free), 1)
    for kind, day in zip(quality, q_days, strict=False):
        budget = min(share + 1.0, long_km - 0.5) if long_km else share + 1.0
        w = build_workout(kind, day, budget, inp, week.phase)
        workouts.append(w)
        remaining -= w.km
    easy_days = [d for d in free if d not in q_days]
    per_easy = _round_km(remaining / len(easy_days)) if easy_days else 0
    if long_km:
        per_easy = min(per_easy, max(long_km - 1.0, 3.0))
    for day in easy_days:
        workouts.append(build_workout("easy", day, per_easy, inp, week.phase))
    return sorted(workouts, key=lambda w: w.day)


def generate(inp: PlanInput) -> list[Week]:
    """Plan completo: semanas con fase, volumen y sesiones."""
    total = math.ceil(((inp.race_date - inp.start).days + 1) / 7)
    if total < MIN_WEEKS:
        raise ValueError(f"Faltan menos de {MIN_WEEKS} semanas para la carrera: no da tiempo a un plan completo.")
    total = min(total, MAX_WEEKS)
    start = inp.race_date - timedelta(days=inp.race_date.weekday()) - timedelta(weeks=total - 1)
    phase_list = phases(total, inp.distance_m)
    volumes = weekly_volumes(phase_list, inp.current_km_week, peak_km(inp.distance_m, inp.current_km_week))
    weeks = []
    for idx, (phase, (km, recovery)) in enumerate(zip(phase_list, volumes, strict=True)):
        week = Week(index=idx + 1, start=start + timedelta(weeks=idx), phase=phase, target_km=km,
                    is_recovery=recovery)  # fmt: skip
        week.workouts = week_workouts(week, inp)
        weeks.append(week)
    return weeks


# ─── Adaptación semanal ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class Adjustment:
    action: str  # progress | hold | reduce
    factor: float  # multiplica el volumen previsto de la semana siguiente
    reason: str


def adjustment(done_ratio: float | None, compliance: float | None, tsb: float | None, acwr: float | None) -> Adjustment:
    """
    Decide cómo seguir la semana próxima según lo cumplido y cómo llegas.

    Args:
        done_ratio: sesiones hechas / planificadas en la semana que acaba (None si no había).
        compliance: cumplimiento medio (0–100) de las sesiones hechas.
        tsb: frescura actual. acwr: carga reciente frente a la habitual.
    """
    if (acwr is not None and acwr > 1.5) or (tsb is not None and tsb < -30):
        return Adjustment("reduce", 0.8, "Tu carga reciente se ha disparado: bajamos un 20 % y cambiamos una sesión "
                                         "de calidad por un rodaje suave para que asimiles el trabajo.")  # fmt: skip
    if done_ratio is not None and done_ratio < 0.5:
        return Adjustment("reduce", 0.85, "La semana pasada hiciste menos de la mitad de las sesiones: retomamos con "
                                          "un 15 % menos para no forzar la vuelta.")  # fmt: skip
    if (
        (acwr is not None and acwr > 1.3)
        or (tsb is not None and tsb < -10)
        or (done_ratio is not None and done_ratio < 0.8)
    ):
        return Adjustment("hold", 1.0, "Mantenemos el volumen previsto sin subir: llegas algo cargado o no "
                                       "completaste todas las sesiones.")  # fmt: skip
    if compliance is not None and compliance < 70:
        return Adjustment("hold", 1.0, "Las sesiones salieron bastante distintas de lo previsto: repetimos el nivel "
                                       "antes de progresar.")  # fmt: skip
    if done_ratio is None:
        return Adjustment("progress", 1.0, "Primera semana del plan: empezamos según lo previsto.")
    return Adjustment("progress", 1.0, "Semana cumplida y llegas fresco: seguimos el plan como estaba previsto.")
