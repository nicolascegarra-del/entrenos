"""borrar actividades (marca para no volver a importarlas)

Revision ID: a9c3e5b7d1f8
Revises: f2b6c8d4a1e3
Create Date: 2026-10-24 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "a9c3e5b7d1f8"
down_revision: str | None = "f2b6c8d4a1e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "deleted_activity",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(length=24), nullable=False),
        sa.Column("external_key", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_s", sa.Float(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_deleted_activity_user_id"), "deleted_activity", ["user_id"], unique=False)
    op.create_index(op.f("ix_deleted_activity_start_time"), "deleted_activity", ["start_time"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_deleted_activity_start_time"), table_name="deleted_activity")
    op.drop_index(op.f("ix_deleted_activity_user_id"), table_name="deleted_activity")
    op.drop_table("deleted_activity")
