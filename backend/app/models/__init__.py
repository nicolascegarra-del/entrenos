"""Importa todos los modelos para que Alembic y SQLModel.metadata los registren."""

from app.models.account import GarminCredential, GarminStatus, Invitation, Sex, UserProfile, WeightLog
from app.models.achievement import Achievement
from app.models.activity import Activity, ActivityRaw, ActivityStream, DeletedActivity, Device, Lap
from app.models.admin import AppSetting, AuditLog, EmailVerification, PasswordReset
from app.models.ai import (
    ActivityReview,
    AiProvider,
    AiProviderConfig,
    AiReviewSettings,
    ChatConversation,
    ChatMessage,
)
from app.models.coach import CoachMemory, CoachSettings, PlanProposal, WeeklyCheckin
from app.models.gear import Gear
from app.models.goal import RaceGoal
from app.models.health import AthleteZones, DailyMetric
from app.models.metric import MetricDefinition, MetricScope
from app.models.notification import NotificationLog, NotificationPrefs, PushSubscription
from app.models.oura import (
    DailySeries,
    HealthTag,
    OuraConnection,
    OuraWebhookSubscription,
    RestPeriod,
    WellnessSession,
)
from app.models.performance import PerformanceTest
from app.models.plan import BlockKind, MatchMode, PlannedBlock, PlannedSession
from app.models.planned_route import PlannedRoute
from app.models.settings import RECOVERY_SOURCES, SYNC_INTERVALS, SyncMode, UserSettings
from app.models.sources import (
    AppleImport,
    CorosCredential,
    CorosOAuth,
    DeviceConnection,
    IngestToken,
    OAuthClient,
    OAuthState,
)
from app.models.strength import ActivityFeedback, StrengthSet
from app.models.sync import SyncRun, SyncStatus
from app.models.training import TrainingPlan, TrainingPlanWeek
from app.models.user import AccountTier, User, UserStatus

__all__ = [
    "DailySeries",
    "HealthTag",
    "OuraConnection",
    "OuraWebhookSubscription",
    "RECOVERY_SOURCES",
    "RestPeriod",
    "WellnessSession",
    "ActivityReview",
    "AiReviewSettings",
    "AppleImport",
    "CoachMemory",
    "CoachSettings",
    "PlanProposal",
    "WeeklyCheckin",
    "DeletedActivity",
    "PerformanceTest",
    "CorosCredential",
    "CorosOAuth",
    "DeviceConnection",
    "OAuthClient",
    "OAuthState",
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
    "PlannedRoute",
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
