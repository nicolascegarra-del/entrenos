"""rutas planificadas en el mapa (inicio, puntos de paso y fin) y su sesión del plan

Revision ID: c4e8a2f6b1d9
Revises: b3d7f9a1c5e2
Create Date: 2026-10-25 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4e8a2f6b1d9"
down_revision: str | None = "b3d7f9a1c5e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = sqlmodel.sql.sqltypes.AutoString
NOW = sa.text("now()")
JSONB = postgresql.JSONB(astext_type=sa.Text())
EMPTY = sa.text("'[]'")


def upgrade() -> None:
    op.create_table(
        "planned_route",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", S(length=120), nullable=False),
        sa.Column("mode", S(length=16), nullable=False),
        sa.Column("waypoints", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("geometry", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("profile", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("surfaces", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("waytypes", JSONB, server_default=EMPTY, nullable=False),
        sa.Column("distance_m", sa.Integer(), nullable=False),
        sa.Column("ascent_m", sa.Integer(), nullable=False),
        sa.Column("descent_m", sa.Integer(), nullable=False),
        sa.Column("estimated_s", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_planned_route_user_id"), "planned_route", ["user_id"], unique=False)
    op.add_column("planned_session", sa.Column("planned_route_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_planned_session_planned_route_id"), "planned_session", ["planned_route_id"], unique=False)
    op.create_foreign_key(
        "planned_session_planned_route_id_fkey", "planned_session", "planned_route", ["planned_route_id"], ["id"],
        ondelete="SET NULL",
    )  # fmt: skip


def downgrade() -> None:
    op.drop_constraint("planned_session_planned_route_id_fkey", "planned_session", type_="foreignkey")
    op.drop_index(op.f("ix_planned_session_planned_route_id"), table_name="planned_session")
    op.drop_column("planned_session", "planned_route_id")
    op.drop_index(op.f("ix_planned_route_user_id"), table_name="planned_route")
    op.drop_table("planned_route")
