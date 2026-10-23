"""tests fase 2: preferencia de lactato

Revision ID: d8a3b1c5e7f2
Revises: c4d2e8f1a6b3
Create Date: 2026-10-24 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8a3b1c5e7f2"
down_revision: str | None = "c4d2e8f1a6b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_profile", sa.Column("lactate_tests", sa.Boolean(), server_default=sa.true(), nullable=False))


def downgrade() -> None:
    op.drop_column("user_profile", "lactate_tests")
