from datetime import datetime

from sqlalchemy import Column, DateTime, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field


class PushSubscription(SQLModel, table=True):
    """Suscripción Web Push de un dispositivo (navegador o PWA instalada)."""

    __tablename__ = "push_subscription"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    endpoint: str = Field(sa_column=Column(Text, nullable=False, unique=True))
    p256dh: str = Field(max_length=256)
    auth: str = Field(max_length=64)
    user_agent: str = Field(default="", max_length=255)
    created_at: datetime = created_at_field()
    last_ok_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class NotificationPrefs(SQLModel, table=True):
    """Qué avisos quiere recibir cada persona. Sin fila, todos activados a las 7:00."""

    __tablename__ = "notification_prefs"

    user_id: int = Field(foreign_key="user.id", primary_key=True, ondelete="CASCADE")
    daily_session: bool = True  # «hoy toca…» a la hora elegida
    daily_hour: int = Field(default=7, ge=0, le=23)
    timezone: str = Field(default="Europe/Madrid", max_length=64)
    overload: bool = True  # riesgo de lesión en «Atención»
    sync_error: bool = True  # sincronización fallida o Garmin desconectado
    achievements: bool = True  # récords y logros
    plan_changes: bool = True  # ajuste semanal del plan automático


class NotificationLog(SQLModel, table=True):
    """Avisos enviados: evita repetir el mismo (p. ej. un aviso de sobrecarga por semana)."""

    __tablename__ = "notification_log"
    __table_args__ = (UniqueConstraint("user_id", "key"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    kind: str = Field(max_length=32)
    key: str = Field(max_length=120)
    title: str = Field(max_length=120)
    sent_at: datetime = created_at_field()
