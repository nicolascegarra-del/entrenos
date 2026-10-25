"""valoración (útil / no útil) de las respuestas del asistente

Revision ID: d5f9b3a7c2e4
Revises: c4e8a2f6b1d9
Create Date: 2026-10-25 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5f9b3a7c2e4"
down_revision: str | None = "c4e8a2f6b1d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chat_message", sa.Column("feedback", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_message", "feedback")
