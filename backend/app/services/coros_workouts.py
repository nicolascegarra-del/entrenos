"""
Enviar sesiones del plan al calendario de COROS (y de ahí al reloj) por su MCP oficial.

Formato (`createScheduledWorkout`, leído del propio servidor): un `course` con `sportType` (1 carrera,
2 bici, 5 trail), nombre, descripción y `sections`. Cada sección: `sectionType` (1 calentamiento,
2 trabajo, 3 recuperación, 4 vuelta a la calma), `targetType` (1 distancia en m, 2 tiempo en s,
4 libre: hasta pulsar vuelta) con `targetValue`, e intensidad opcional con `intensityType`
(1 FC, 2 ritmo en s/km, 4 potencia) y un rango absoluto `intensityValueStart/End`. Las series van en
un `intervalGroup` con `repeats` (1-20) y `sets` (trabajo y recuperación), sin anidar.

Limitaciones de COROS: solo de hoy a 90 días vista, y no se puede mover ni borrar un entreno desde
fuera. Si cambian los bloques se actualiza (`updateScheduledWorkout`, reemplazo completo); si cambia
el día, se crea en el nuevo y la persona debe quitar el antiguo en la app de COROS.
"""

import logging
import re
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from sqlmodel import Session

from app.models import PlannedBlock, PlannedSession
from app.services.plan_service import blocks_of
from app.services.plan_steps import sport_family
from app.services.workout_export import APP_NAME, WorkoutExportError, content_hash

logger = logging.getLogger(__name__)

MAX_DAYS_AHEAD = 90
MAX_REPEATS = 20
_SECTION = {"warmup": 1, "interval": 2, "steady": 2, "recovery": 3, "cooldown": 4}
_PACE_RANGE = (120, 1499)
_HR_RANGE = (30, 240)
_POWER_RANGE = (10, 2000)


class CorosTarget(Protocol):
    def call(self, name: str, arguments: dict) -> object: ...


def _sport(sport: str) -> int:
    family = sport_family(sport)
    if family == "running":
        return 1  # el trail de COROS no admite objetivos de tiempo: se envía como carrera
    if family == "cycling":
        return 2
    raise WorkoutExportError("A COROS solo se pueden enviar sesiones de carrera y de bici.")


def _clamp(value: float, bounds: tuple[int, int]) -> int:
    return max(bounds[0], min(bounds[1], round(value)))


def _intensity(block: PlannedBlock, sport: int) -> dict:
    """Rango absoluto de ritmo (s/km), FC o potencia; COROS no admite cadencia ni velocidad en bici."""
    lo, hi = block.target_min, block.target_max
    if lo is None and hi is None:
        return {}
    lo = lo if lo is not None else hi
    hi = hi if hi is not None else lo
    metric = block.target_metric
    if metric == "speed" and sport == 1:  # km/h → ritmo
        metric, lo, hi = "pace", 3600 / hi, 3600 / lo  # type: ignore[operator]
    if metric == "pace" and sport == 1:
        kind, bounds = 2, _PACE_RANGE
    elif metric == "hr":
        kind, bounds = 1, _HR_RANGE
    elif metric == "power":
        kind, bounds = 4, _POWER_RANGE
    else:
        return {}
    a, b = sorted((_clamp(lo, bounds), _clamp(hi, bounds)))  # type: ignore[arg-type]
    return {"intensityType": kind, "intensityValueStart": a, "intensityValueEnd": b}


def _target(duration: float | None, distance: float | None) -> dict:
    if distance:
        return {"targetType": 1, "targetValue": max(1, round(distance))}
    if duration:
        return {"targetType": 2, "targetValue": max(1, round(duration))}
    return {"targetType": 4}  # libre: se termina con el botón de vuelta


def coros_course(planned: PlannedSession, blocks: list[PlannedBlock]) -> dict:
    """
    `course` de COROS a partir de los bloques de la sesión.

    Raises:
        WorkoutExportError: deporte sin soporte o sesión sin bloques.
    """
    sport = _sport(planned.sport)
    if not blocks:
        raise WorkoutExportError("La sesión no tiene bloques que enviar.")
    sections: list[dict] = []
    for b in blocks:
        work = {"sectionType": _SECTION.get(b.kind, 2), **_target(b.duration_s, b.distance_m),
                **_intensity(b, sport)}  # fmt: skip
        if b.repeat > 1:
            work["sectionType"] = 2 if work["sectionType"] not in (2, 3) else work["sectionType"]
            sets = [work]
            if b.recovery_duration_s or b.recovery_distance_m:
                sets.append({"sectionType": 3, **_target(b.recovery_duration_s, b.recovery_distance_m)})
            sections.append({"intervalGroup": True, "repeats": min(b.repeat, MAX_REPEATS), "sets": sets})
        else:
            sections.append(work)
    notes = planned.notes.strip()
    return {
        "courseName": planned.title[:100] or "Sesión",
        "courseDescription": (notes or f"{planned.title}.")[:900] + f"\n\nDesde {APP_NAME}.",
        "sportType": sport,
        "sections": sections,
    }


def _ymd(day: date) -> str:
    return day.strftime("%Y%m%d")


_ID = re.compile(r"idInPlan\D{0,6}(\d{6,})", re.IGNORECASE)


def id_in_plan(result: object) -> str:
    """El idInPlan del resultado (viene como texto para asistentes o como JSON)."""
    if isinstance(result, dict):
        for key in ("idInPlan", "id_in_plan"):
            if result.get(key):
                return str(result[key])
        result = str(result)
    match = _ID.search(str(result))
    return match.group(1) if match else ""


def send(session: Session, planned: PlannedSession, mcp: CorosTarget, today: date | None = None) -> str:
    """
    Envía (o actualiza) la sesión en el calendario de COROS.

    Returns:
        "sent", "unchanged" o "error" (con el motivo en la sesión).
    """
    today = today or date.today()

    def fail(message: str) -> str:
        planned.coros_status, planned.coros_error = "error", message[:255]
        session.add(planned)
        session.commit()
        return "error"

    try:
        course = coros_course(planned, blocks_of(session, planned))
    except WorkoutExportError as exc:
        return fail(str(exc))
    if not today <= planned.day <= today + timedelta(days=MAX_DAYS_AHEAD):
        return fail("COROS solo admite sesiones de hoy a 90 días vista.")
    digest = content_hash(planned, {"coros": course})
    if planned.coros_status == "sent" and planned.coros_hash == digest:
        return "unchanged"
    same_day = planned.coros_id_in_plan and planned.coros_day == planned.day
    try:
        if same_day:
            result = mcp.call(
                "updateScheduledWorkout",
                {"date": _ymd(planned.day), "idInPlan": planned.coros_id_in_plan, "course": course},
            )
        else:
            result = mcp.call("createScheduledWorkout", {"date": _ymd(planned.day), "course": course})
    except Exception as exc:  # noqa: BLE001 - el motivo de COROS llega en el mensaje
        logger.warning("COROS: fallo al enviar la sesión %s (%s: %s)", planned.id, type(exc).__name__, str(exc)[:300])
        return fail(str(exc) or "COROS no aceptó el entreno. Inténtalo más tarde.")
    new_id = id_in_plan(result) or (planned.coros_id_in_plan if same_day else "")
    if not new_id:
        logger.info("COROS: respuesta sin idInPlan: %s", str(result)[:300])
    moved = bool(planned.coros_id_in_plan) and not same_day
    planned.coros_id_in_plan, planned.coros_day = new_id, planned.day
    planned.coros_status, planned.coros_hash = "sent", digest
    planned.coros_error = "Has cambiado el día: quita el entreno del día anterior en la app de COROS." if moved else ""
    planned.coros_sent_at = datetime.now(UTC)
    session.add(planned)
    session.commit()
    return "sent"


def send_upcoming(session: Session, user_id: int, mcp: CorosTarget, today: date | None = None) -> dict[str, int]:
    """Las sesiones de los próximos 7 días (las mismas que se mandan a Garmin)."""
    from app.services.garmin_workouts import upcoming

    counts = {"sent": 0, "unchanged": 0, "error": 0}
    for planned in upcoming(session, user_id, today):
        counts[send(session, planned, mcp, today)] += 1
    return counts
