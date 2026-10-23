"""
Tests de rendimiento: protocolos, detección de resultados en una actividad y confirmación.

Un test se crea de tres formas: a mano (resultado conocido), marcando una actividad («Es un test») o
planificando una sesión de test que, al sincronizar el entreno emparejado, se analiza sola y avisa.

La detección busca en las series de la actividad el mejor tramo que pide el protocolo (p. ej. 30 min
seguidos), calcula los valores y pasa comprobaciones de calidad. Un fallo **crítico** (no hay tramo
de esa duración, faltan datos) deja el test como `failed`; los demás bajan la confianza y se explican,
pero se puede confirmar igual. Solo al confirmar cuenta para las zonas (ver `test_results`).

Fórmulas:
- 30 min a tope (Friel): ritmo umbral = ritmo medio de los 30 min; FC umbral = FC media de los
  últimos 20 min.
- 20 min a tope: el 95 % del ritmo (más lento) y de la FC media (aproximación habitual).
- Cooper (12 min): VO2max = (distancia − 504,9) / 44,73.
- Contrarreloj 5K / 10K: VDOT de Daniels y su ritmo T como umbral.
- Velocidad crítica (3 + 12 min): CS = (d12 − d3) / (720 − 180); umbral = 96 % de la CS.
- FC máxima: el máximo de la FC media en 10 s (filtra picos falsos del sensor).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlmodel import Session, col, select

from app.models import Activity, ActivityStream, PerformanceTest, PlannedSession
from app.services.plan_steps import local_day, sport_family
from app.services.race_models import daniels_paces, vdot
from app.services.zones import CS_TO_THRESHOLD, hr_zones

MAX_STEP_SPEED = 12.0  # m/s: avances más rápidos entre dos puntos son saltos de GPS
MAX_GAP_S = 30
MIN_HR_COVERAGE = 0.8
EVEN_PACE_TOLERANCE = 0.08  # ±8 % entre tercios del tramo
COHERENCE_TOLERANCE = 0.15  # ±15 % respecto a lo que la app ya estimaba
HARD_EFFORT_OF_HR_MAX = 0.85
HR_PEAK_WINDOW_S = 10
VALID_RANGES = {
    "lthr": (100, 210),
    "threshold_pace_s_km": (150, 600),
    "vo2max": (20, 90),
    "hr_max": (120, 230),
    "vdot": (20, 90),
}


# ─── Protocolos ──────────────────────────────────────────────────────────────


def _blocks(*items: tuple) -> list[dict]:
    """Plantilla de bloques para la sesión del plan: (tipo, duración s, distancia m, repeticiones, recuperación s)."""
    out = []
    for kind, duration, distance, *rest in items:
        repeat = rest[0] if rest else 1
        recovery = rest[1] if len(rest) > 1 else None
        out.append({"kind": kind, "repeat": repeat, "duration_s": duration, "distance_m": distance,
                    "recovery_duration_s": recovery})  # fmt: skip
    return out


@dataclass(frozen=True)
class Protocol:
    key: str
    label: str
    sport: str
    summary: str  # qué saca
    how: str  # cómo se hace
    template: list[dict] = field(default_factory=list)
    detectable: bool = True


WARMUP, COOLDOWN = ("warmup", 900, None), ("cooldown", 600, None)
PROTOCOLS: dict[str, Protocol] = {
    p.key: p
    for p in (
        Protocol("run_30min", "30 min a tope", "running", "Ritmo y FC de umbral",
                 "Tras calentar, 30 min al máximo ritmo que puedas mantener de forma regular, en llano y solo.",
                 _blocks(WARMUP, ("steady", 1800, None), COOLDOWN)),
        Protocol("run_20min", "20 min a tope", "running", "Ritmo y FC de umbral (aprox.)",
                 "Tras calentar, 20 min a tope y regulares. Más corto que el de 30 min, algo menos preciso.",
                 _blocks(WARMUP, ("steady", 1200, None), COOLDOWN)),
        Protocol("cooper", "Test de Cooper (12 min)", "running", "VO2max estimado",
                 "Tras calentar, corre la máxima distancia posible en 12 minutos, mejor en pista.",
                 _blocks(WARMUP, ("steady", 720, None), COOLDOWN)),
        Protocol("tt_5k", "Contrarreloj 5K", "running", "VDOT, ritmos de entrenamiento y umbral",
                 "Tras calentar, 5 km a tope en un recorrido llano.",
                 _blocks(WARMUP, ("steady", None, 5000), COOLDOWN)),
        Protocol("tt_10k", "Contrarreloj 10K", "running", "VDOT, ritmos de entrenamiento y umbral",
                 "Tras calentar, 10 km a tope en un recorrido llano.",
                 _blocks(WARMUP, ("steady", None, 10000), COOLDOWN)),
        Protocol("critical_speed", "Velocidad crítica (3 + 12 min)", "running",
                 "Umbral y reserva anaeróbica (D′)",
                 "Tras calentar, 3 min a tope, 15-30 min suaves para recuperar y 12 min a tope.",
                 _blocks(WARMUP, ("interval", 180, None), ("recovery", 1200, None), ("interval", 720, None),
                         COOLDOWN)),
        Protocol("max_hr", "FC máxima (cuestas)", "running", "FC máxima real (afina todas las zonas)",
                 "Tras calentar bien, 3 cuestas de 2-3 min cada vez más fuertes; la última, a tope.",
                 _blocks(WARMUP, ("interval", 150, None, 3, 180), COOLDOWN)),
        Protocol("bike_hr_30min", "Bici: 30 min a tope (FC)", "cycling", "FC de umbral en bici",
                 "Tras calentar, 30 min al máximo esfuerzo sostenible (rodillo o puerto regular).",
                 _blocks(WARMUP, ("steady", 1800, None), COOLDOWN)),
        Protocol("bike_hr_20min", "Bici: 20 min a tope (FC)", "cycling", "FC de umbral en bici (aprox.)",
                 "Tras calentar, 20 min al máximo esfuerzo sostenible.",
                 _blocks(WARMUP, ("steady", 1200, None), COOLDOWN)),
        Protocol("manual", "Resultado conocido", "running", "Lo que ya sabes (otro test, un informe…)",
                 "Mete a mano los valores que tengas: FC umbral, ritmo umbral, VO2max o FC máxima.",
                 detectable=False),
    )
}  # fmt: skip
MANUAL_KEYS = ("lthr", "threshold_pace_s_km", "vo2max", "hr_max")


class TestError(ValueError):
    """Petición de test no válida (protocolo desconocido, deporte que no encaja…)."""


# ─── Series y tramos ─────────────────────────────────────────────────────────


@dataclass
class Series:
    t: list[float]
    d: list[float | None]  # distancia acumulada «limpia» (None si la actividad no tiene)
    hr: list[float | None]
    # Sumas acumuladas de FC y de puntos con FC: la media de cualquier tramo en O(1).
    _hr_sum: list[float] = field(default_factory=list)
    _hr_n: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        total, n = 0.0, 0
        self._hr_sum, self._hr_n = [0.0], [0]
        for h in self.hr:
            if h:
                total, n = total + h, n + 1
            self._hr_sum.append(total)
            self._hr_n.append(n)

    @classmethod
    def load(cls, session: Session, activity_id: int) -> "Series":
        rows = session.exec(
            select(ActivityStream).where(
                ActivityStream.activity_id == activity_id, col(ActivityStream.channel).in_(("time", "distance", "hr"))
            )
        ).all()
        ch = {r.channel: r.values for r in rows}
        time, dist, hr = ch.get("time") or [], ch.get("distance") or [], ch.get("hr") or []
        t_out, d_out, h_out = [], [], []
        last_d: float | None = None
        clean = 0.0
        for i, t in enumerate(time):
            if t is None:
                continue
            d = dist[i] if i < len(dist) else None
            if d is not None:
                if last_d is not None and t_out:
                    clean += min(max(d - last_d, 0.0), MAX_STEP_SPEED * max(t - t_out[-1], 0.0))
                last_d = d
            t_out.append(float(t))
            d_out.append(clean if last_d is not None else None)
            h = hr[i] if i < len(hr) else None
            h_out.append(float(h) if h else None)
        return cls(t_out, d_out, h_out)

    @property
    def has_distance(self) -> bool:
        return any(v is not None for v in self.d) and (self.d[-1] or 0) > 0

    def hr_stats(self, i: int, j: int) -> tuple[float | None, float]:
        """FC media del tramo y fracción de puntos con FC."""
        count = self._hr_n[j + 1] - self._hr_n[i]
        points = j - i + 1
        avg = (self._hr_sum[j + 1] - self._hr_sum[i]) / count if count else None
        return avg, (count / points if points else 0.0)

    def max_gap(self, i: int, j: int) -> float:
        return max((self.t[k + 1] - self.t[k] for k in range(i, j)), default=0.0)

    def index_at(self, t: float) -> int:
        return next((k for k, v in enumerate(self.t) if v >= t), len(self.t) - 1)


def best_by_duration(s: Series, duration: float, score: Callable[[int, int], float | None]) -> tuple[int, int] | None:
    """Tramo de `duration` s (el primer punto que la alcanza) con la mayor puntuación."""
    best, best_ij, j = None, None, 0
    for i in range(len(s.t)):
        j = max(j, i)
        while j < len(s.t) - 1 and s.t[j] - s.t[i] < duration:
            j += 1
        if s.t[j] - s.t[i] < duration:
            break
        value = score(i, j)
        if value is not None and (best is None or value > best):
            best, best_ij = value, (i, j)
    return best_ij


def fastest_distance(s: Series, distance: float) -> tuple[int, int] | None:
    """El tramo más rápido que cubre `distance` metros."""
    best, best_ij, j = None, None, 0
    for i in range(len(s.t)):
        if s.d[i] is None:
            continue
        j = max(j, i)
        while j < len(s.t) - 1 and (s.d[j] is None or s.d[j] - s.d[i] < distance):
            j += 1
        if s.d[j] is None or s.d[j] - s.d[i] < distance:
            break
        span = s.t[j] - s.t[i]
        if best is None or span < best:
            best, best_ij = span, (i, j)
    return best_ij


def _speed(s: Series, i: int, j: int) -> float | None:
    if s.d[i] is None or s.d[j] is None or s.t[j] <= s.t[i]:
        return None
    return (s.d[j] - s.d[i]) / (s.t[j] - s.t[i])


def _pace(speed: float) -> int:
    return round(1000 / speed)


# ─── Comprobaciones ──────────────────────────────────────────────────────────


@dataclass
class Outcome:
    results: dict = field(default_factory=dict)
    checks: list[dict] = field(default_factory=list)
    window: tuple[float, float] | None = None  # segundos desde el inicio, para enseñarlo

    def check(self, key: str, ok: bool, message: str, critical: bool = False) -> bool:
        self.checks.append({"key": key, "ok": ok, "message": message, "critical": critical})
        return ok

    @property
    def failed(self) -> bool:
        return any(c["critical"] and not c["ok"] for c in self.checks)

    @property
    def confidence(self) -> str:
        if self.failed:
            return "baja"
        misses = sum(not c["ok"] for c in self.checks)
        return "alta" if misses == 0 else "media" if misses == 1 else "baja"


def _check_window(o: Outcome, s: Series, ij: tuple[int, int] | None, label: str) -> bool:
    if not o.check("duracion", ij is not None, f"Tramo de {label} encontrado." if ij else
                   f"La actividad no tiene {label} seguidos con datos.", critical=True):  # fmt: skip
        return False
    i, j = ij  # type: ignore[misc]
    o.window = (s.t[i], s.t[j])
    gap = s.max_gap(i, j)
    o.check("datos", gap <= MAX_GAP_S, "Sin cortes en los datos." if gap <= MAX_GAP_S else
            f"Hay un corte de {round(gap)} s en el tramo (¿pausa o pérdida de señal?).")  # fmt: skip
    return True


def _check_even(o: Outcome, s: Series, i: int, j: int) -> None:
    """Ritmo regular: cada tercio del tramo, a ±8 % de la media."""
    total = _speed(s, i, j)
    if not total:
        return
    edges = [s.index_at(s.t[i] + (s.t[j] - s.t[i]) * k / 3) for k in range(4)]
    parts = [_speed(s, a, b) for a, b in zip(edges, edges[1:], strict=False) if b > a]
    parts = [p for p in parts if p]
    worst = max((abs(p - total) / total for p in parts), default=0.0)
    o.check("regularidad", worst <= EVEN_PACE_TOLERANCE, "Ritmo regular de principio a fin." if
            worst <= EVEN_PACE_TOLERANCE else
            f"El ritmo varió un {round(worst * 100)} % entre tramos: el resultado puede salir desviado.")  # fmt: skip


def _check_effort(o: Outcome, avg_hr: float | None, hr_max: float | None) -> None:
    if avg_hr is None or not hr_max:
        return
    ok = avg_hr >= HARD_EFFORT_OF_HR_MAX * hr_max
    o.check("esfuerzo", ok, "La FC confirma un esfuerzo a tope." if ok else
            f"La FC media ({round(avg_hr)}) es baja para un test a tope (tu FC máx. es {round(hr_max)}).")  # fmt: skip


def _check_coherence(o: Outcome, current: dict) -> None:
    """Muy lejos de lo que ya estimaba la app suele ser un error de datos (o un test mal hecho)."""
    far = []
    for key, label in (("lthr", "FC umbral"), ("threshold_pace_s_km", "ritmo umbral")):
        new, old = o.results.get(key), current.get(key)
        if new and old and abs(new - old) / old > COHERENCE_TOLERANCE:
            far.append(f"{label} un {round(abs(new - old) / old * 100)} % distinta")
    o.check("coherencia", not far, "Encaja con tus datos recientes." if not far else
            "Sale " + " y ".join(far) + " de lo que estimábamos: revísalo antes de aplicarlo.")  # fmt: skip


def _check_ranges(o: Outcome) -> None:
    bad = [k for k, v in o.results.items() if k in VALID_RANGES and not VALID_RANGES[k][0] <= v <= VALID_RANGES[k][1]]
    for k in bad:
        o.results.pop(k)
    if bad:
        o.check("valores", False, "Algún valor salía fuera de lo posible y se ha descartado.", critical=not o.results)


# ─── Detección por protocolo ─────────────────────────────────────────────────


def _threshold_run(s: Series, duration: int, factor: float, last_s: int | None) -> Outcome:
    o = Outcome()
    if not o.check("distancia", s.has_distance, "Con distancia." if s.has_distance else
                   "La actividad no tiene distancia: no se puede calcular el ritmo.", critical=True):  # fmt: skip
        return o
    ij = best_by_duration(s, duration, lambda i, j: _speed(s, i, j))
    if not _check_window(o, s, ij, f"{duration // 60} min"):
        return o
    i, j = ij  # type: ignore[misc]
    speed = _speed(s, i, j)
    if speed:
        o.results["threshold_pace_s_km"] = _pace(speed * factor)
    hr_from = s.index_at(s.t[j] - last_s) if last_s else i
    avg_hr, coverage = s.hr_stats(hr_from, j)
    if o.check("pulso", coverage >= MIN_HR_COVERAGE and avg_hr is not None, "Con pulso." if
               coverage >= MIN_HR_COVERAGE else "Sin pulso suficiente: solo se calcula el ritmo."):  # fmt: skip
        o.results["lthr"] = round(avg_hr * factor)  # type: ignore[operator]
    _check_even(o, s, i, j)
    o.results["_avg_hr"] = s.hr_stats(i, j)[0]
    return o


def _threshold_bike(s: Series, duration: int, factor: float, last_s: int | None) -> Outcome:
    """Sin potencia: el tramo de mayor FC media; FC umbral = FC media (de los últimos 20 min)."""
    o = Outcome()

    def score(i: int, j: int) -> float | None:
        avg, coverage = s.hr_stats(i, j)
        return avg if coverage >= MIN_HR_COVERAGE else None

    ij = best_by_duration(s, duration, score)
    if not _check_window(o, s, ij, f"{duration // 60} min con pulso"):
        return o
    i, j = ij  # type: ignore[misc]
    hr_from = s.index_at(s.t[j] - last_s) if last_s else i
    avg_hr, _ = s.hr_stats(hr_from, j)
    if avg_hr:
        o.results["lthr"] = round(avg_hr * factor)
        o.results["hr_zones"] = hr_zones(o.results["lthr"])
    # Esfuerzo sostenido: la FC del último tercio no debe caer respecto al primero.
    third = (s.t[j] - s.t[i]) / 3
    first, _ = s.hr_stats(i, s.index_at(s.t[i] + third))
    last, _ = s.hr_stats(s.index_at(s.t[j] - third), j)
    if first and last:
        o.check("regularidad", last >= first - 3, "Esfuerzo sostenido hasta el final." if last >= first - 3 else
                "La FC bajó al final: ¿aflojaste? El umbral puede salir bajo.")  # fmt: skip
    o.results["_avg_hr"] = s.hr_stats(i, j)[0]
    return o


def _cooper(s: Series) -> Outcome:
    o = Outcome()
    if not o.check("distancia", s.has_distance, "Con distancia." if s.has_distance else
                   "La actividad no tiene distancia.", critical=True):  # fmt: skip
        return o
    ij = best_by_duration(s, 720, lambda i, j: _speed(s, i, j))
    if not _check_window(o, s, ij, "12 min"):
        return o
    i, j = ij  # type: ignore[misc]
    meters = (s.d[j] or 0) - (s.d[i] or 0)
    o.results["vo2max"] = round((meters - 504.9) / 44.73, 1)
    o.results["distance_m"] = round(meters)
    _check_even(o, s, i, j)
    o.results["_avg_hr"] = s.hr_stats(i, j)[0]
    return o


def _time_trial(s: Series, meters: int) -> Outcome:
    o = Outcome()
    if not o.check("distancia", s.has_distance, "Con distancia." if s.has_distance else
                   "La actividad no tiene distancia.", critical=True):  # fmt: skip
        return o
    ij = fastest_distance(s, meters)
    if not _check_window(o, s, ij, f"{meters // 1000} km"):
        return o
    i, j = ij  # type: ignore[misc]
    seconds = s.t[j] - s.t[i]
    v = vdot(meters, seconds)
    fast, slow = daniels_paces(v)["threshold"]
    o.results.update({"vdot": round(v, 1), "time_s": round(seconds), "threshold_pace_s_km": round((fast + slow) / 2)})
    _check_even(o, s, i, j)
    o.results["_avg_hr"] = s.hr_stats(i, j)[0]
    return o


def _critical_speed(s: Series) -> Outcome:
    o = Outcome()
    if not o.check("distancia", s.has_distance, "Con distancia." if s.has_distance else
                   "La actividad no tiene distancia.", critical=True):  # fmt: skip
        return o
    short = best_by_duration(s, 180, lambda i, j: _speed(s, i, j))
    long = best_by_duration(s, 720, lambda i, j: _speed(s, i, j))
    if not _check_window(o, s, long, "12 min") or short is None:
        o.check("duracion", short is not None, "Falta el esfuerzo de 3 min.", critical=True)
        return o
    v3, v12 = _speed(s, *short), _speed(s, *long)
    if not v3 or not v12:
        return o
    d3, d12 = v3 * 180, v12 * 720
    cs = (d12 - d3) / (720 - 180)
    d_prime = d3 - cs * 180
    ok = 0 < cs < v12 < v3 and d_prime > 0
    if o.check("coherencia_cs", ok, "Los dos esfuerzos encajan." if ok else
               "El esfuerzo de 3 min no fue más rápido que el de 12: repite el test.", critical=True):  # fmt: skip
        o.results.update({"cs_speed": round(cs, 3), "d_prime_m": round(d_prime),
                          "threshold_pace_s_km": _pace(cs * CS_TO_THRESHOLD)})  # fmt: skip
    return o


def _max_hr(s: Series) -> Outcome:
    o = Outcome()

    def score(i: int, j: int) -> float | None:
        avg, coverage = s.hr_stats(i, j)
        return avg if coverage >= MIN_HR_COVERAGE else None

    ij = best_by_duration(s, HR_PEAK_WINDOW_S, score)
    if o.check("pulso", ij is not None, "Con pulso." if ij else "La actividad no tiene pulso.", critical=True):
        avg, _ = s.hr_stats(*ij)  # type: ignore[misc]
        o.results["hr_max"] = round(avg)  # type: ignore[arg-type]
        o.window = (s.t[ij[0]], s.t[ij[1]])  # type: ignore[index]
    return o


DETECTORS: dict[str, Callable[[Series], Outcome]] = {
    "run_30min": lambda s: _threshold_run(s, 1800, 1.0, 1200),
    "run_20min": lambda s: _threshold_run(s, 1200, 0.95, None),
    "cooper": _cooper,
    "tt_5k": lambda s: _time_trial(s, 5000),
    "tt_10k": lambda s: _time_trial(s, 10000),
    "critical_speed": _critical_speed,
    "max_hr": _max_hr,
    "bike_hr_30min": lambda s: _threshold_bike(s, 1800, 1.0, 1200),
    "bike_hr_20min": lambda s: _threshold_bike(s, 1200, 0.95, None),
}


def detect(session: Session, activity: Activity, protocol: str) -> Outcome:
    """Analiza la actividad con el protocolo y devuelve resultados y comprobaciones (sin guardar nada)."""
    from app.services import progress as prog
    from app.services.zones import estimate_thresholds

    o = DETECTORS[protocol](Series.load(session, activity.id))
    avg_hr = o.results.pop("_avg_hr", None)
    if o.failed:
        return o
    thr = prog.user_thresholds(session, activity.user_id)
    if protocol != "max_hr":
        _check_effort(o, avg_hr, thr.hr_max)
    if PROTOCOLS[protocol].sport == "running" and protocol != "max_hr":
        current = estimate_thresholds(session, activity.user_id)
        _check_coherence(o, {"lthr": current["lthr"], "threshold_pace_s_km": current["threshold_pace_s_km"]})
    _check_ranges(o)
    return o


# ─── Crear, confirmar y listar ───────────────────────────────────────────────


def _sport_ok(protocol: Protocol, activity: Activity) -> bool:
    return sport_family(activity.sport) == sport_family(protocol.sport)


def test_from_activity(
    session: Session, activity: Activity, protocol_key: str, planned: PlannedSession | None = None
) -> PerformanceTest:
    """
    Marca la actividad como test (o vuelve a analizarla con otro protocolo) y guarda lo detectado.

    Raises:
        TestError: protocolo desconocido o de otro deporte, o la actividad ya tiene un test confirmado.
    """
    protocol = PROTOCOLS.get(protocol_key)
    if protocol is None or not protocol.detectable:
        raise TestError("Ese tipo de test no se puede detectar en una actividad.")
    if not _sport_ok(protocol, activity):
        raise TestError(f"«{protocol.label}» es un test de otro deporte.")
    row = session.exec(select(PerformanceTest).where(PerformanceTest.activity_id == activity.id)).first()
    if row is not None and row.status == "confirmed":
        raise TestError("Esta actividad ya tiene un test confirmado: bórralo primero para repetirlo.")
    outcome = detect(session, activity, protocol_key)
    day = local_day(activity.start_time, activity.timezone)
    row = row or PerformanceTest(user_id=activity.user_id, activity_id=activity.id, sport=protocol.sport,
                                 protocol=protocol_key, test_date=day)  # fmt: skip
    row.protocol, row.sport = protocol_key, protocol.sport
    row.source = "planned" if planned else "activity"
    row.planned_session_id = planned.id if planned else row.planned_session_id
    row.status = "failed" if outcome.failed else "detected"
    row.confidence, row.checks = outcome.confidence, outcome.checks
    row.results = {**outcome.results, **({"window_s": list(outcome.window)} if outcome.window else {})}
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def manual_test(
    session: Session, user_id: int, sport: str, test_date: date, values: dict, notes: str = ""
) -> PerformanceTest:
    """Resultado conocido metido a mano: queda confirmado (se fía de quien lo mete) y se aplica."""
    results = {k: values[k] for k in MANUAL_KEYS if values.get(k) is not None}
    bad = [k for k, v in results.items() if not VALID_RANGES[k][0] <= v <= VALID_RANGES[k][1]]
    if bad or not results:
        raise TestError("Revisa los valores: alguno está fuera de lo posible." if bad else "Mete al menos un valor.")
    if sport_family(sport) == "cycling" and "lthr" in results:
        results["hr_zones"] = hr_zones(results["lthr"])
    row = PerformanceTest(user_id=user_id, sport=sport, protocol="manual", test_date=test_date, source="manual",
                          status="confirmed", confidence="alta", results=results, notes=notes[:500],
                          confirmed_at=datetime.now(UTC))  # fmt: skip
    session.add(row)
    session.commit()
    session.refresh(row)
    _apply(session, row)
    return row


def confirm(session: Session, row: PerformanceTest) -> PerformanceTest:
    """Da por bueno el test detectado: desde ahora cuenta para las zonas (8 semanas)."""
    if row.status == "failed":
        raise TestError("Este test no se pudo calcular: no hay valores que aplicar.")
    row.status, row.confirmed_at = "confirmed", datetime.now(UTC)
    session.add(row)
    session.commit()
    _apply(session, row)
    session.refresh(row)
    return row


def _apply(session: Session, row: PerformanceTest) -> None:
    """Recalcula las zonas de carrera (las de bici van con el propio test)."""
    from app.services.zones import refresh_zones

    if sport_family(row.sport) == "running" or row.results.get("hr_max"):
        refresh_zones(session, row.user_id)


def user_tests(session: Session, user_id: int, limit: int = 50) -> list[PerformanceTest]:
    return list(
        session.exec(
            select(PerformanceTest)
            .where(PerformanceTest.user_id == user_id)
            .order_by(col(PerformanceTest.test_date).desc(), col(PerformanceTest.id).desc())
            .limit(limit)
        ).all()
    )


# ─── Sesiones de test del plan ───────────────────────────────────────────────


def detect_planned(session: Session, user_id: int) -> int:
    """
    Tras emparejar el plan: las sesiones de test con actividad y aún sin analizar se analizan y avisan.

    Returns:
        Cuántos tests nuevos se han detectado.
    """
    from app.services.notifications import notify

    rows = session.exec(
        select(PlannedSession).where(
            PlannedSession.user_id == user_id,
            col(PlannedSession.test_protocol).is_not(None),
            col(PlannedSession.activity_id).is_not(None),
        )
    ).all()
    done = set(
        session.exec(
            select(PerformanceTest.activity_id).where(
                PerformanceTest.user_id == user_id, col(PerformanceTest.activity_id).is_not(None)
            )
        ).all()
    )
    found = 0
    for planned in rows:
        activity = session.get(Activity, planned.activity_id)
        protocol = PROTOCOLS.get(planned.test_protocol or "")
        if activity is None or activity.id in done or protocol is None or not _sport_ok(protocol, activity):
            continue
        row = test_from_activity(session, activity, protocol.key, planned)
        found += 1
        title = f"Resultado de tu test: {protocol.label}"
        body = (summary_text(row) + ". Revísalo y aplícalo a tus zonas.") if row.status == "detected" else (
            "No se pudo calcular: " + next((c["message"] for c in row.checks if not c["ok"]), "revisa la actividad.")
        )  # fmt: skip
        try:
            notify(session, user_id, "test", f"test:{row.id}", title, body, f"/actividades/{activity.id}")
        except Exception:  # noqa: BLE001 - el aviso es secundario
            session.rollback()
    return found


def _mmss(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def summary_text(row: PerformanceTest) -> str:
    """Resumen corto de los resultados («FC umbral 172 · ritmo umbral 4:05/km»)."""
    r = row.results
    parts = []
    if r.get("lthr"):
        parts.append(f"FC umbral {r['lthr']}")
    if r.get("threshold_pace_s_km"):
        parts.append(f"ritmo umbral {_mmss(r['threshold_pace_s_km'])}/km")
    if r.get("vo2max"):
        parts.append(f"VO2max {r['vo2max']}")
    if r.get("vdot"):
        parts.append(f"VDOT {r['vdot']}")
    if r.get("hr_max"):
        parts.append(f"FC máx. {r['hr_max']}")
    return " · ".join(parts) or "Sin valores"


def protocols_out() -> list[dict]:
    return [
        {"key": p.key, "label": p.label, "sport": p.sport, "summary": p.summary, "how": p.how,
         "detectable": p.detectable, "template": p.template}
        for p in PROTOCOLS.values()
    ]  # fmt: skip
