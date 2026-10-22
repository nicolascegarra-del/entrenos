from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field, jsonb_field, utcnow


class AiProvider(StrEnum):
    OPENAI = "openai"
    GEMINI = "gemini"
    ANTHROPIC = "anthropic"


class AiProviderConfig(SQLModel, table=True):
    """
    Cuenta de un asistente de IA de un usuario: su propia clave de API (cifrada con
    Fernet; nunca vuelve al cliente) y el modelo elegido. Una por proveedor y usuario.
    """

    __tablename__ = "ai_provider_config"
    __table_args__ = (UniqueConstraint("user_id", "provider"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    provider: AiProvider = Field(sa_column=Column(String(16), nullable=False))
    model: str = Field(max_length=100)
    key_enc: str = Field(sa_column=Column(Text, nullable=False))
    key_last4: str = Field(max_length=4)  # para reconocer la clave sin mostrarla
    enabled: bool = True
    is_default: bool = False
    created_at: datetime = created_at_field()
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=utcnow)
    )


class ChatConversation(SQLModel, table=True):
    """Conversación con el asistente (el título es el inicio de la primera pregunta)."""

    __tablename__ = "chat_conversation"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    title: str = Field(max_length=120)
    created_at: datetime = created_at_field()
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=utcnow)
    )


class ChatMessage(SQLModel, table=True):
    """Mensaje de una conversación; los del asistente guardan proveedor, modelo y tokens consumidos."""

    __tablename__ = "chat_message"

    id: int | None = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="chat_conversation.id", index=True, ondelete="CASCADE")
    role: str = Field(max_length=16)  # user | assistant
    content: str = Field(sa_column=Column(Text, nullable=False))
    provider: str | None = Field(default=None, max_length=16)
    model: str | None = Field(default=None, max_length=100)
    input_tokens: int | None = None
    output_tokens: int | None = None
    tools: list | None = jsonb_field(nullable=True)  # datos que consultó el asistente (etiquetas)
    created_at: datetime = created_at_field()
