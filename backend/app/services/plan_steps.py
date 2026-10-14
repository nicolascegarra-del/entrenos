"""Expansión de bloques planificados en pasos y utilidades de deporte/fecha local."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.models import BlockKind, PlannedBlock

# Deportes que se consideran equivalentes al emparejar plan ↔ actividad.
_FAMILIES = {
    "running": {"running", "trail_running", "treadmill_running", "track_running", "indoor_running", "street_running"},
    "cycling": {
        "cycling",
        "road_biking",
        "mountain_biking",
        "indoor_cycling",
        "gravel_cycling",
        "virtual_ride",
        "cyclocross",
    },
    "swimming": {"lap_swimming", "open_water_swimming", "swimming"},
    "strength": {"strength_training"},
}

TARGET_METRICS = ("pace", "speed", "hr", "power", "cadence")


def sport_family(sport: str) -> str:
    return next((family for family, members in _FAMILIES.items() if sport in members), sport)


def local_day(start_time: datetime, timezone: str | None) -> date:
    """Día local de una actividad a partir de su inicio UTC y su offset ("+02:00")."""
    if timezone and len(timezone) == 6 and timezone[0] in "+-":
        sign = 1 if timezone[0] == "+" else -1
        offset = timedelta(hours=int(timezone[1:3]), minutes=int(timezone[4:6])) * sign
        return (start_time + offset).date()
    return start_time.date()


@dataclass(frozen=True)
class Step:
    """Un paso ejecutable: una repetición o una recuperación concreta."""

    block_position: int
    kind: str
    rep: int  # 1..repeat (0 en bloques sin repeticiones)
    duration_s: float | None
    distance_m: float | None
    target_metric: str | None = None
    target_min: float | None = None
    target_max: float | None = None

    @property
    def has_target(self) -> bool:
        return self.target_metric is not None and (self.target_min is not None or self.target_max is not None)

    @property
    def label(self) -> str:
        names = {
            BlockKind.WARMUP: "Calentamiento",
            BlockKind.STEADY: "Continuo",
            BlockKind.INTERVAL: "Serie",
            BlockKind.RECOVERY: "Recuperación",
            BlockKind.COOLDOWN: "Vuelta a la calma",
        }
        base = names.get(BlockKind(self.kind), self.kind)
        return f"{base} {self.rep}" if self.rep else base


def expand_steps(blocks: list[PlannedBlock]) -> list[Step]:
    """
    Convierte bloques en la secuencia de pasos que se ejecutan.

    Ej. "6 x 1000 m + 90 s rec." → 6 series y 5 recuperaciones intercaladas.
    """
    steps: list[Step] = []
    for block in sorted(blocks, key=lambda b: b.position):
        has_recovery = block.recovery_duration_s or block.recovery_distance_m
        for rep in range(1, block.repeat + 1):
            steps.append(
                Step(
                    block_position=block.position,
                    kind=block.kind,
                    rep=rep if block.repeat > 1 else 0,
                    duration_s=block.duration_s,
                    distance_m=block.distance_m,
                    target_metric=block.target_metric,
                    target_min=block.target_min,
                    target_max=block.target_max,
                )
            )
            if has_recovery and rep < block.repeat:
                steps.append(
                    Step(
                        block_position=block.position,
                        kind=BlockKind.RECOVERY,
                        rep=rep,
                        duration_s=block.recovery_duration_s,
                        distance_m=block.recovery_distance_m,
                    )
                )
    return steps


def estimated_duration_s(steps: list[Step]) -> float:
    """Duración aproximada del plan (los pasos por distancia se estiman a 6:00 /km si no hay ritmo)."""
    total = 0.0
    for step in steps:
        if step.duration_s:
            total += step.duration_s
        elif step.distance_m:
            pace = 360.0
            if step.target_metric == "pace" and step.target_min and step.target_max:
                pace = (step.target_min + step.target_max) / 2
            total += step.distance_m / 1000 * pace
    return total
