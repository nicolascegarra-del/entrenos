"""Importa todos los modelos para que Alembic y SQLModel.metadata los registren."""

from app.models.activity import Activity, ActivityRaw, ActivityStream, Device, Lap
from app.models.health import AthleteZones, DailyMetric
from app.models.metric import MetricDefinition, MetricScope
from app.models.plan import BlockKind, MatchMode, PlannedBlock, PlannedSession
from app.models.settings import SYNC_INTERVALS, SyncMode, UserSettings
from app.models.sync import SyncRun, SyncStatus
from app.models.user import User

__all__ = [
    "Activity",
    "ActivityRaw",
    "ActivityStream",
    "AthleteZones",
    "BlockKind",
    "DailyMetric",
    "Device",
    "Lap",
    "MatchMode",
    "MetricDefinition",
    "MetricScope",
    "PlannedBlock",
    "PlannedSession",
    "SYNC_INTERVALS",
    "SyncMode",
    "SyncRun",
    "SyncStatus",
    "User",
    "UserSettings",
]
