"""
Sesión planificada → entreno estructurado para el reloj.

Dos salidas a partir de los mismos bloques (calentamiento, series con repeticiones y recuperación,
vuelta a la calma; cada uno por tiempo, distancia o «hasta pulsar vuelta» y con objetivo opcional):

- **Garmin Connect** (`garmin_workout`): el JSON del servicio de entrenos de Garmin. Se sube y se
  programa en el calendario; el reloj lo recibe al sincronizar.
- **Fichero .FIT de entreno** (`fit_workout`): el formato estándar que importan Garmin (por USB),
  Wahoo, Hammerhead, Suunto, COROS y otros. Se escribe a mano (mensajes file_id, workout y
  workout_step del perfil FIT), sin dependencias.

Objetivos: ritmo (s/km) → rango de velocidad en m/s (Garmin «pace.zone», FIT velocidad en mm/s);
velocidad (km/h); FC (ppm); potencia (W); cadencia. Si solo hay un límite, se usa en los dos.
"""

import hashlib
import json
import struct
from datetime import UTC, datetime

from app.models import PlannedBlock, PlannedSession
from app.services.plan_steps import estimated_duration_s, expand_steps, sport_family

SUPPORTED = ("running", "cycling")
APP_NAME = "APP ENTRENOS"


class WorkoutExportError(ValueError):
    """La sesión no se puede convertir (deporte sin soporte o sin bloques)."""


def _family(sport: str) -> str:
    family = sport_family(sport)
    if family not in SUPPORTED:
        raise WorkoutExportError("De momento solo se pueden enviar al reloj sesiones de carrera y de bici.")
    return family


def _range(block: PlannedBlock) -> tuple[float, float] | None:
    lo, hi = block.target_min, block.target_max
    if lo is None and hi is None:
        return None
    lo = lo if lo is not None else hi
    hi = hi if hi is not None else lo
    return (min(lo, hi), max(lo, hi))  # type: ignore[type-var]


def _speed_range(block: PlannedBlock) -> tuple[float, float] | None:
    """Rango de velocidad en m/s (lento, rápido) para ritmo o velocidad."""
    r = _range(block)
    if r is None:
        return None
    if block.target_metric == "pace":
        return (1000 / r[1], 1000 / r[0])  # el ritmo más lento es la velocidad más baja
    if block.target_metric == "speed":
        return (r[0] / 3.6, r[1] / 3.6)
    return None


# ─── Garmin Connect ──────────────────────────────────────────────────────────

_SPORT = {
    "running": {"sportTypeId": 1, "sportTypeKey": "running"},
    "cycling": {"sportTypeId": 2, "sportTypeKey": "cycling"},
}
_STEP = {
    "warmup": (1, "warmup"),
    "cooldown": (2, "cooldown"),
    "interval": (3, "interval"),
    "steady": (3, "interval"),
    "recovery": (4, "recovery"),
}
_NO_TARGET = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target"}


def _condition(duration: float | None, distance: float | None) -> tuple[dict, float | None]:
    if distance:
        return {"conditionTypeId": 3, "conditionTypeKey": "distance"}, float(distance)
    if duration:
        return {"conditionTypeId": 2, "conditionTypeKey": "time"}, float(duration)
    return {"conditionTypeId": 1, "conditionTypeKey": "lap.button"}, None


def _target(block: PlannedBlock) -> dict:
    """Objetivo del paso en el formato de Garmin (rango personalizado)."""
    metric = block.target_metric
    if metric in ("pace", "speed") and (speeds := _speed_range(block)):
        key = (6, "pace.zone") if metric == "pace" else (5, "speed.zone")
        return {"targetType": {"workoutTargetTypeId": key[0], "workoutTargetTypeKey": key[1]},
                "targetValueOne": round(speeds[0], 3), "targetValueTwo": round(speeds[1], 3)}  # fmt: skip
    keys = {"hr": (4, "heart.rate.zone"), "power": (2, "power.zone"), "cadence": (3, "cadence")}
    if metric in keys and (r := _range(block)):
        return {"targetType": {"workoutTargetTypeId": keys[metric][0], "workoutTargetTypeKey": keys[metric][1]},
                "targetValueOne": r[0], "targetValueTwo": r[1]}  # fmt: skip
    return {"targetType": _NO_TARGET}


def _executable(order: int, kind: str, duration: float | None, distance: float | None, target: dict,
                child: int | None = None) -> dict:  # fmt: skip
    type_id, type_key = _STEP.get(kind, (3, "interval"))
    condition, value = _condition(duration, distance)
    step = {"type": "ExecutableStepDTO", "stepOrder": order,
            "stepType": {"stepTypeId": type_id, "stepTypeKey": type_key},
            "endCondition": condition, "endConditionValue": value, **target}  # fmt: skip
    if child is not None:
        step["childStepId"] = child
    return {k: v for k, v in step.items() if v is not None}


def garmin_workout(planned: PlannedSession, blocks: list[PlannedBlock]) -> dict:
    """
    JSON del entreno para `upload_workout` de Garmin Connect.

    Raises:
        WorkoutExportError: deporte sin soporte o sesión sin bloques.
    """
    family = _family(planned.sport)
    if not blocks:
        raise WorkoutExportError("La sesión no tiene bloques que enviar.")
    steps: list[dict] = []
    order, group = 0, 0
    for b in blocks:
        target = _target(b)
        if b.repeat > 1:
            group += 1
            order += 1
            repeat = {"type": "RepeatGroupDTO", "stepOrder": order,
                      "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat"}, "childStepId": group,
                      "numberOfIterations": b.repeat, "smartRepeat": False,
                      "endCondition": {"conditionTypeId": 7, "conditionTypeKey": "iterations"},
                      "endConditionValue": float(b.repeat), "workoutSteps": []}  # fmt: skip
            order += 1
            repeat["workoutSteps"].append(_executable(order, b.kind, b.duration_s, b.distance_m, target, group))
            if b.recovery_duration_s or b.recovery_distance_m:
                order += 1
                repeat["workoutSteps"].append(
                    _executable(
                        order,
                        "recovery",
                        b.recovery_duration_s,
                        b.recovery_distance_m,
                        {"targetType": _NO_TARGET},
                        group,
                    )  # fmt: skip
                )
                repeat["skipLastRestStep"] = True  # la recuperación va entre repeticiones, no tras la última
            steps.append(repeat)
        else:
            order += 1
            steps.append(_executable(order, b.kind, b.duration_s, b.distance_m, target))
    sport = _SPORT[family]
    description = " ".join(x for x in (planned.notes.strip(), f"Desde {APP_NAME}.") if x)
    return {
        "workoutName": planned.title[:80],
        "description": description[:500],
        "sportType": sport,
        "estimatedDurationInSecs": round(estimated_duration_s(expand_steps(blocks))),
        "workoutSegments": [{"segmentOrder": 1, "sportType": sport, "workoutSteps": steps}],
    }


def content_hash(planned: PlannedSession, workout: dict) -> str:
    """Huella de lo que se envía (y del día): si cambia, hay que reenviarlo."""
    raw = json.dumps({"day": planned.day.isoformat(), "w": workout}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]  # noqa: S324 - huella, no seguridad


# ─── Fichero .FIT de entreno ─────────────────────────────────────────────────

FIT_EPOCH = datetime(1989, 12, 31, tzinfo=UTC)
_BASE = {"enum": 0x00, "uint8": 0x02, "uint16": 0x84, "uint32": 0x86, "string": 0x07}
_FMT = {"enum": "B", "uint8": "B", "uint16": "H", "uint32": "I"}
NAME_BYTES = 32
# workout_step: duration_type (time=0, distance=1, open=5, repeat_until_steps_cmplt=6),
# target_type (speed=0, heart_rate=1, open=2, cadence=3, power=4), intensity (recuperación = «rest»,
# que entienden todos los relojes; «recovery» solo los perfiles FIT recientes).
_INTENSITY = {"warmup": 2, "cooldown": 3, "recovery": 1, "interval": 0, "steady": 0}
_SPORT_FIT = {"running": 1, "cycling": 2}
_STEP_NAME = {"warmup": "Calentamiento", "cooldown": "Vuelta a la calma", "interval": "Serie", "steady": "Bloque",
              "recovery": "Recuperación"}  # fmt: skip


def _crc(data: bytes) -> int:
    table = (0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
             0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400)  # fmt: skip
    crc = 0
    for byte in data:
        for nibble in (byte & 0xF, byte >> 4):
            tmp = table[crc & 0xF]
            crc = (crc >> 4) & 0x0FFF
            crc = crc ^ tmp ^ table[nibble]
    return crc


class _FitWriter:
    def __init__(self) -> None:
        self.body = b""
        self.local = 0

    def message(self, global_num: int, fields: list[tuple[int, str, object]], rows: list[list[object]]) -> None:
        """Una definición (tipo local nuevo) y sus filas de datos."""
        local = self.local
        self.local += 1
        defs = b""
        for num, kind, _ in fields:
            size = NAME_BYTES if kind == "string" else struct.calcsize(_FMT[kind])
            defs += struct.pack("BBB", num, size, _BASE[kind])
        self.body += struct.pack("<BBBHB", 0x40 | local, 0, 0, global_num, len(fields)) + defs
        for row in rows:
            data = struct.pack("B", local)
            for (_, kind, _), value in zip(fields, row, strict=True):
                if kind == "string":
                    # Sin partir un carácter de varios bytes al recortar.
                    raw = str(value).encode("utf-8")[: NAME_BYTES - 1].decode("utf-8", "ignore").encode("utf-8")
                    data += raw + b"\x00" * (NAME_BYTES - len(raw))
                else:
                    data += struct.pack("<" + _FMT[kind], value)
            self.body += data

    def bytes(self) -> bytes:
        header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(self.body), b".FIT")
        header += struct.pack("<H", _crc(header))
        data = header + self.body
        return data + struct.pack("<H", _crc(data))


def _fit_target(block: PlannedBlock) -> tuple[int, int, int]:
    """(target_type, bajo, alto) con las unidades del perfil FIT (valores personalizados)."""
    metric = block.target_metric
    if metric in ("pace", "speed") and (speeds := _speed_range(block)):
        return 0, round(speeds[0] * 1000), round(speeds[1] * 1000)  # mm/s
    r = _range(block)
    if r is None:
        return 2, 0, 0
    if metric == "hr":
        return 1, round(r[0]) + 100, round(r[1]) + 100  # FC personalizada: ppm + 100
    if metric == "power":
        return 4, round(r[0]) + 1000, round(r[1]) + 1000  # potencia personalizada: W + 1000
    if metric == "cadence":
        return 3, round(r[0]), round(r[1])
    return 2, 0, 0


def _fit_duration(duration: float | None, distance: float | None) -> tuple[int, int]:
    if distance:
        return 1, round(distance * 100)  # cm
    if duration:
        return 0, round(duration * 1000)  # ms
    return 5, 0  # abierto: hasta pulsar vuelta


def fit_workout(planned: PlannedSession, blocks: list[PlannedBlock]) -> bytes:
    """
    Fichero .FIT de entreno.

    Raises:
        WorkoutExportError: deporte sin soporte o sesión sin bloques.
    """
    family = _family(planned.sport)
    if not blocks:
        raise WorkoutExportError("La sesión no tiene bloques que exportar.")
    rows: list[list[object]] = []
    for b in blocks:
        first = len(rows)
        target, low, high = _fit_target(b)
        dur_type, dur_value = _fit_duration(b.duration_s, b.distance_m)
        rows.append([len(rows), _STEP_NAME.get(b.kind, "Bloque"), dur_type, dur_value,
                     target, 0, low, high, _INTENSITY.get(b.kind, 0)])  # fmt: skip
        if b.repeat > 1:
            if b.recovery_duration_s or b.recovery_distance_m:
                rec_type, rec_value = _fit_duration(b.recovery_duration_s, b.recovery_distance_m)
                rows.append([len(rows), "Recuperación", rec_type, rec_value, 2, 0, 0, 0, 1])
            # Repetir desde el primer paso del bloque hasta completar `repeat` veces.
            rows.append([len(rows), f"Repetir ×{b.repeat}", 6, first, 2, b.repeat, 0, 0, 0])
    w = _FitWriter()
    created = int((datetime.now(UTC) - FIT_EPOCH).total_seconds())
    w.message(0, [(0, "enum", None), (1, "uint16", None), (2, "uint16", None), (4, "uint32", None)],
              [[5, 255, 1, created]])  # fmt: skip  # file_id: tipo workout, fabricante «development»
    w.message(26, [(4, "enum", None), (6, "uint16", None), (8, "string", None)],
              [[_SPORT_FIT[family], len(rows), planned.title]])  # fmt: skip
    step_fields = [(254, "uint16", None), (0, "string", None), (1, "enum", None), (2, "uint32", None),
                   (3, "enum", None), (4, "uint32", None), (5, "uint32", None), (6, "uint32", None),
                   (7, "enum", None)]  # fmt: skip
    w.message(27, step_fields, rows)
    return w.bytes()


def fit_filename(planned: PlannedSession) -> str:
    safe = "".join(c if c.isalnum() else "-" for c in planned.title.lower()).strip("-")[:40] or "sesion"
    return f"{planned.day.isoformat()}-{safe}.fit"
