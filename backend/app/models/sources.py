from datetime import datetime

from sqlalchemy import Column, DateTime, Text
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field


class CorosCredential(SQLModel, table=True):
    """
    Conexión con COROS Training Hub (API web no oficial). Solo se guarda el token de acceso cifrado:
    la contraseña se usa para entrar y se descarta.
    """

    __tablename__ = "coros_credential"

    user_id: int = Field(foreign_key="user.id", primary_key=True, ondelete="CASCADE")
    account: str = Field(max_length=255)
    token_enc: str = Field(sa_column=Column(Text, nullable=False))
    base_url: str = Field(max_length=120)
    status: str = Field(default="ok", max_length=16)  # ok | expired | error
    last_sync_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    last_error: str = Field(default="", max_length=255)
    created_at: datetime = created_at_field()


class IngestToken(SQLModel, table=True):
    """Token personal para recibir datos de Health Connect (app de webhook en Android). Se guarda su hash."""

    __tablename__ = "ingest_token"

    user_id: int = Field(foreign_key="user.id", primary_key=True, ondelete="CASCADE")
    token_hash: str = Field(max_length=64, index=True, unique=True)
    hint: str = Field(max_length=8)  # últimos caracteres, para reconocerlo
    created_at: datetime = created_at_field()
    last_used_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
