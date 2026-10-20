from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime, String
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field


class UserStatus(StrEnum):
    ACTIVE = "active"
    PENDING = "pending"  # registro con aprobación: espera a que un administrador la acepte
    DISABLED = "disabled"  # desactivado por un administrador: no puede entrar ni sincronizar


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(max_length=255, unique=True, index=True)
    password_hash: str = Field(max_length=255)
    is_admin: bool = Field(default=False, sa_column_kwargs={"server_default": "false"})
    status: UserStatus = Field(
        default=UserStatus.ACTIVE, sa_column=Column(String(16), nullable=False, server_default="active")
    )
    # Se incrementa para invalidar todas las sesiones (cambio de contraseña, «cerrar en todos», admin).
    token_version: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    failed_logins: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    locked_until: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    last_login_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    created_at: datetime = created_at_field()
