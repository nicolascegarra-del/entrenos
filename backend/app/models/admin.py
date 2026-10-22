from datetime import datetime

from sqlalchemy import Column, DateTime, Text
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field, jsonb_field, utcnow


class PasswordReset(SQLModel, table=True):
    """Enlace de un solo uso para poner una contraseña nueva (por email o generado por un administrador)."""

    __tablename__ = "password_reset"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    token_hash: str = Field(max_length=64, unique=True)  # SHA-256: el token en claro solo va en el enlace
    created_by: int | None = Field(default=None, foreign_key="user.id", ondelete="SET NULL")
    created_at: datetime = created_at_field()
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    used_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class EmailVerification(SQLModel, table=True):
    """Enlace de un solo uso para confirmar el email de una cuenta autoregistrada."""

    __tablename__ = "email_verification"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    token_hash: str = Field(max_length=64, unique=True)
    created_at: datetime = created_at_field()
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    used_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class AppSetting(SQLModel, table=True):
    """Ajustes globales de la app que cambia un administrador (p. ej. el modo de registro)."""

    __tablename__ = "app_setting"

    key: str = Field(primary_key=True, max_length=64)
    value: str = Field(sa_column=Column(Text, nullable=False))
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=utcnow)
    )


class AuditLog(SQLModel, table=True):
    """
    Registro de acciones de administración. `target_*` no es clave foránea para que la
    entrada sobreviva al borrado del usuario. Nunca guarda contraseñas ni tokens.
    """

    __tablename__ = "audit_log"

    id: int | None = Field(default=None, primary_key=True)
    actor_id: int | None = Field(default=None, foreign_key="user.id", index=True, ondelete="SET NULL")
    actor_email: str | None = Field(default=None, max_length=255)
    action: str = Field(max_length=40)
    target_user_id: int | None = None
    target_email: str | None = Field(default=None, max_length=255)
    detail: dict = jsonb_field()
    created_at: datetime = created_at_field()
