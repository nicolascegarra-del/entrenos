"""relojes y pulseras por cuenta de la marca: Suunto, Amazfit (Zepp) y Xiaomi (Mi Fitness)

Revision ID: e8b4c2a6d1f3
Revises: d7a3e5c1b9f4
Create Date: 2026-10-31 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8b4c2a6d1f3"
down_revision: str | None = "d7a3e5c1b9f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "device_connection",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("account", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("session_enc", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ok"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "provider"),
    )
    op.create_index("ix_device_connection_user_id", "device_connection", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_device_connection_user_id", table_name="device_connection")
    op.drop_table("device_connection")
