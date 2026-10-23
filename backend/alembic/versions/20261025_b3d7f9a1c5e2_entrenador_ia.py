"""entrenador ia: ficha del atleta, revisión semanal y propuestas del plan

Revision ID: b3d7f9a1c5e2
Revises: a9c3e5b7d1f8
Create Date: 2026-10-25 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b3d7f9a1c5e2"
down_revision: str | None = "a9c3e5b7d1f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = sqlmodel.sql.sqltypes.AutoString
NOW = sa.text("now()")
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "coach_settings",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("health_consent", sa.Boolean(), nullable=False),
        sa.Column("health_consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("interview_done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("weekly_review", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "coach_memory",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category", S(length=16), nullable=False),
        sa.Column("content", S(length=500), nullable=False),
        sa.Column("source", S(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_coach_memory_user_id"), "coach_memory", ["user_id"], unique=False)
    op.create_table(
        "weekly_checkin",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("status", S(length=16), nullable=False),
        sa.Column("answers", JSONB, server_default=sa.text("'{}'"), nullable=False),
        sa.Column("summary", sa.Text(), server_default="", nullable=False),
        sa.Column("error", S(length=255), nullable=False),
        sa.Column("effects", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "week_start"),
    )
    op.create_index(op.f("ix_weekly_checkin_user_id"), "weekly_checkin", ["user_id"], unique=False)
    op.create_table(
        "plan_proposal",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("planned_session_id", sa.Integer(), nullable=False),
        sa.Column("change", JSONB, server_default=sa.text("'{}'"), nullable=False),
        sa.Column("reason", S(length=500), nullable=False),
        sa.Column("status", S(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["planned_session_id"], ["planned_session.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_plan_proposal_user_id"), "plan_proposal", ["user_id"], unique=False)
    op.create_index(op.f("ix_plan_proposal_planned_session_id"), "plan_proposal", ["planned_session_id"], unique=False)
    op.add_column("chat_message", sa.Column("effects", JSONB, nullable=True))
    op.add_column(
        "notification_prefs", sa.Column("weekly_review", sa.Boolean(), server_default=sa.true(), nullable=False)
    )


def downgrade() -> None:
    op.drop_column("notification_prefs", "weekly_review")
    op.drop_column("chat_message", "effects")
    op.drop_table("plan_proposal")
    op.drop_table("weekly_checkin")
    op.drop_table("coach_memory")
    op.drop_table("coach_settings")
