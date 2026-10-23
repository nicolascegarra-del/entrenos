"""Importa todos los modelos para que Alembic y SQLModel.metadata los registren."""

from app.models.account import GarminCredential, GarminStatus, Invitation, Sex, UserProfile, WeightLog
from app.models.achievement import Achievement
from app.models.activity import Activity, ActivityRaw, ActivityStream, Device, Lap
from app.models.admin import AppSetting, AuditLog, EmailVerification, PasswordReset
from app.models.ai import (
    ActivityReview,
    AiProvider,
    AiProviderConfig,
    AiReviewSettings,
    ChatConversation,
    ChatMessage,
)
from app.models.gear import Gear
from app.models.goal import RaceGoal
from app.models.health import AthleteZones, DailyMetric
from app.models.metric import MetricDefinition, MetricScope
from app.models.notification import NotificationLog, NotificationPrefs, PushSubscription
from app.models.plan import BlockKind, MatchMode, PlannedBlock, PlannedSession
from app.models.settings import SYNC_INTERVALS, SyncMode, UserSettings
from app.models.sources import AppleImport, CorosCredential, IngestToken
from app.models.strength import ActivityFeedback, StrengthSet
from app.models.sync import SyncRun, SyncStatus
from app.models.training import TrainingPlan, TrainingPlanWeek
from app.models.user import AccountTier, User, UserStatus

__all__ = [
    "ActivityReview",
    "AiReviewSettings",
    "AppleImport",
    "CorosCredential",
    "IngestToken",
    "Achievement",
    "AiProvider",
    "AiProviderConfig",
    "ChatConversation",
    "ChatMessage",
    "GarminCredential",
    "GarminStatus",
    "Invitation",
    "Sex",
    "UserProfile",
    "WeightLog",
    "Activity",
    "ActivityFeedback",
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
    "Gear",
    "NotificationLog",
    "NotificationPrefs",
    "PushSubscription",
    "RaceGoal",
    "SYNC_INTERVALS",
    "StrengthSet",
    "SyncMode",
    "SyncRun",
    "SyncStatus",
    "TrainingPlan",
    "TrainingPlanWeek",
    "User",
    "UserStatus",
    "AccountTier",
    "AppSetting",
    "EmailVerification",
    "AuditLog",
    "PasswordReset",
    "UserSettings",
]
