from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, DateTime, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field


def utcnow() -> datetime:
    return datetime.now(UTC)


def created_at_field() -> Any:
    return Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )


def jsonb_field(nullable: bool = False) -> Any:
    """Campo JSONB; los no anulables arrancan como objeto vacío."""
    if nullable:
        return Field(default=None, sa_column=Column(JSONB, nullable=True))
    return Field(default_factory=dict, sa_column=Column(JSONB, nullable=False, server_default=text("'{}'")))
