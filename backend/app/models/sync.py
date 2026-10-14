from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime, Index, String
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field


class SyncStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"


class SyncRun(SQLModel, table=True):
    """Historial de sincronizaciones con Garmin (estado visible en Ajustes)."""

    __tablename__ = "sync_run"
    __table_args__ = (Index("ix_sync_run_user_started", "user_id", "started_at"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    started_at: datetime = created_at_field()
    finished_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    status: SyncStatus = Field(default=SyncStatus.RUNNING, sa_column=Column(String(16), nullable=False))
    new_activities: int = 0
    daily_days: int = 0
    error: str | None = Field(default=None, max_length=500)
