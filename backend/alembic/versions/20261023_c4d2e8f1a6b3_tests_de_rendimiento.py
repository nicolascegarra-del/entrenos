"""tests de rendimiento

Revision ID: c4d2e8f1a6b3
Revises: a7e1c3d9b2f4
Create Date: 2026-10-23 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4d2e8f1a6b3"
down_revision: str | None = "a7e1c3d9b2f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "performance_test",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("sport", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("protocol", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("test_date", sa.Date(), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=True),
        sa.Column("planned_session_id", sa.Integer(), nullable=True),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
        sa.Column("confidence", sqlmodel.sql.sqltypes.AutoString(length=8), nullable=False),
        sa.Column("results", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("checks", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("notes", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["activity_id"], ["activity.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["planned_session_id"], ["planned_session.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_performance_test_user_id"), "performance_test", ["user_id"], unique=False)
    op.create_index(op.f("ix_performance_test_activity_id"), "performance_test", ["activity_id"], unique=False)
    op.create_index(
        op.f("ix_performance_test_planned_session_id"), "performance_test", ["planned_session_id"], unique=False
    )
    op.add_column(
        "planned_session", sa.Column("test_protocol", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=True)
    )
    op.add_column("notification_prefs", sa.Column("tests", sa.Boolean(), server_default=sa.true(), nullable=False))


def downgrade() -> None:
    op.drop_column("notification_prefs", "tests")
    op.drop_column("planned_session", "test_protocol")
    op.drop_index(op.f("ix_performance_test_planned_session_id"), table_name="performance_test")
    op.drop_index(op.f("ix_performance_test_activity_id"), table_name="performance_test")
    op.drop_index(op.f("ix_performance_test_user_id"), table_name="performance_test")
    op.drop_table("performance_test")
