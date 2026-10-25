"""módulos por usuario (lo que el administrador fija para cada cuenta)

Revision ID: e6a1c4b8d2f0
Revises: d5f9b3a7c2e4
Create Date: 2026-10-25 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e6a1c4b8d2f0"
down_revision: str | None = "d5f9b3a7c2e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column("module_overrides", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("user", "module_overrides")
