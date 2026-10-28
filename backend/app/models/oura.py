"""
Anillo Oura y datos de salud de alta resolución (de Oura o de otras fuentes en el futuro).

- `OuraConnection`: la conexión OAuth de cada persona (tokens cifrados, nunca en claro).
- `OuraWebhookSubscription`: suscripciones de la app a los webhooks de Oura (son de la app, no de una persona).
- `DailySeries`: series de un día (FC continua, hipnograma, movimiento, MET…) por fuente y tipo.
- `WellnessSession`: sesiones de meditación, respiración, descanso… (no son entrenos).
- `HealthTag`: etiquetas que la persona apunta (alcohol, enfermedad, cafeína…).
- `RestPeriod`: periodos de «modo descanso» (enfermedad, lesión, viaje…).
"""

from datetime import date, datetime

from sqlalchemy import Column, DateTime, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field, jsonb_field


class OuraConnection(SQLModel, table=True):
    """Conexión con Oura (OAuth2). Solo se guardan los tokens cifrados."""

    __tablename__ = "oura_connection"

    user_id: int = Field(foreign_key="user.id", primary_key=True, ondelete="CASCADE")
    oura_user_id: str = Field(default="", max_length=64, index=True)  # `id` de personal_info (llega en webhooks)
    access_token_enc: str = Field(sa_column=Column(Text, nullable=False))
    refresh_token_enc: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    expires_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    scopes: str = Field(default="", max_length=255)  # separados por espacios, como los da Oura
    status: str = Field(default="ok", max_length=16)  # ok | expired | error
    last_error: str = Field(default="", max_length=255)
    last_sync_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    connected_at: datetime = created_at_field()
    history_status: str = Field(default="idle", max_length=16)  # idle | running | done | error
    history_from: date | None = None
    history_to: date | None = None
    # Anillo: modelo, color, talla, firmware y la última batería leída (y cuándo se avisó de batería baja).
    ring: dict = jsonb_field()


class OuraWebhookSubscription(SQLModel, table=True):
    """Suscripción de la app a un tipo de dato y evento de Oura (caduca: se renueva sola)."""

    __tablename__ = "oura_webhook_subscription"
    __table_args__ = (UniqueConstraint("data_type", "event_type", "callback_url"),)

    id: int | None = Field(default=None, primary_key=True)
    remote_id: str = Field(max_length=64, unique=True)
    data_type: str = Field(max_length=40)
    event_type: str = Field(max_length=16)  # create | update | delete
    callback_url: str = Field(max_length=500)
    expiration_time: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    created_at: datetime = created_at_field()


class DailySeries(SQLModel, table=True):
    """
    Serie de un día por fuente y tipo (`kind`):

    - `heartrate`: [[epoch_s, bpm, origen]] (origen de Oura: awake, rest, sleep, workout, live, session).
    - `hypnogram_5min` / `hypnogram_30s`: {"start", "phases": "4433221…"} (1 profundo, 2 ligero, 3 REM, 4 despierto).
    - `movement_30s`: {"start", "values": "1122…"}.
    - `sleep_hr` / `sleep_hrv` / `met`: {"start", "interval", "items": [...]}.
    - `activity_class_5min`: {"start", "classes": "0011223…"}.
    """

    __tablename__ = "daily_series"
    __table_args__ = (UniqueConstraint("user_id", "day", "source", "kind"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    day: date = Field(index=True)
    source: str = Field(max_length=24)
    kind: str = Field(max_length=32)
    data: dict = jsonb_field()


class WellnessSession(SQLModel, table=True):
    """Sesión de meditación, respiración, relajación, siesta guiada… (de la app de Oura)."""

    __tablename__ = "wellness_session"
    __table_args__ = (UniqueConstraint("user_id", "source", "external_id"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    source: str = Field(max_length=24)
    external_id: str = Field(max_length=120)
    type: str = Field(default="", max_length=32)
    start: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    end: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    mood: str | None = Field(default=None, max_length=16)
    hr_avg: float | None = None
    hrv_avg: float | None = None
    raw: dict = jsonb_field()


class HealthTag(SQLModel, table=True):
    """Etiqueta apuntada por la persona (alcohol, cafeína, enfermedad, viaje…)."""

    __tablename__ = "health_tag"
    __table_args__ = (UniqueConstraint("user_id", "source", "external_id"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    source: str = Field(max_length=24)
    external_id: str = Field(max_length=120)
    day: date = Field(index=True)
    start: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    end: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    label: str = Field(default="", max_length=120)
    comment: str = Field(default="", max_length=500)
    raw: dict = jsonb_field()


class RestPeriod(SQLModel, table=True):
    """Periodo de «modo descanso» (enfermedad, lesión, viaje): la carga no debería exigir nada."""

    __tablename__ = "rest_period"
    __table_args__ = (UniqueConstraint("user_id", "source", "external_id"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    source: str = Field(max_length=24)
    external_id: str = Field(max_length=120)
    start_date: date
    end_date: date | None = None  # None = sigue activo
    raw: dict = jsonb_field()
