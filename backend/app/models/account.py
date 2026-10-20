from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field, utcnow


class Sex(StrEnum):
    MALE = "male"
    FEMALE = "female"


class UserProfile(SQLModel, table=True):
    """
    Datos personales que afinan los cálculos: edad (FC máx., percentiles, ajuste por edad),
    sexo (percentiles y ajuste por edad), peso (calorías) y altura (IMC). Se guarda la
    fecha de nacimiento, no la edad, para que la edad se calcule siempre bien.
    """

    __tablename__ = "user_profile"

    user_id: int = Field(foreign_key="user.id", primary_key=True, ondelete="CASCADE")
    birth_date: date | None = None
    sex: Sex | None = Field(default=None, sa_column=Column(String(8)))
    weight_kg: float | None = Field(default=None, gt=0, lt=400)
    height_cm: float | None = Field(default=None, gt=0, lt=260)
    source: str = Field(default="manual", max_length=16)  # garmin | manual
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=utcnow)
    )


class WeightLog(SQLModel, table=True):
    """Historial de peso: una entrada por día cuando cambia (perfil manual o Garmin)."""

    __tablename__ = "weight_log"
    __table_args__ = (UniqueConstraint("user_id", "day"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    day: date
    weight_kg: float = Field(gt=0, lt=400)
    source: str = Field(default="manual", max_length=16)


class GarminStatus(StrEnum):
    OK = "ok"
    EXPIRED = "expired"  # Garmin rechazó los tokens: hay que reconectar


class GarminCredential(SQLModel, table=True):
    """Tokens de sesión de Garmin cifrados (Fernet). La contraseña nunca se guarda."""

    __tablename__ = "garmin_credential"

    user_id: int = Field(foreign_key="user.id", primary_key=True, ondelete="CASCADE")
    tokens_enc: str = Field(sa_column=Column(Text, nullable=False))
    status: GarminStatus = Field(default=GarminStatus.OK, sa_column=Column(String(16), nullable=False))
    display_name: str | None = Field(default=None, max_length=120)
    connected_at: datetime = created_at_field()
    last_ok_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class Invitation(SQLModel, table=True):
    """Invitación de un administrador para que otra persona cree su usuario (enlace de un solo uso)."""

    __tablename__ = "invitation"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(max_length=255, index=True)
    token_hash: str = Field(max_length=64, unique=True)  # SHA-256 del token: el token en claro solo va en el enlace
    created_by: int = Field(foreign_key="user.id", ondelete="CASCADE")
    created_at: datetime = created_at_field()
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    used_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    used_by: int | None = Field(default=None, foreign_key="user.id", ondelete="SET NULL")
