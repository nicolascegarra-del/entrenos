"""enviar entrenos al reloj

Revision ID: e1f4a7b2c9d6
Revises: d8a3b1c5e7f2
Create Date: 2026-10-24 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "e1f4a7b2c9d6"
down_revision: str | None = "d8a3b1c5e7f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("planned_session", sa.Column("garmin_workout_id", sa.BigInteger(), nullable=True))
    op.add_column("planned_session", sa.Column("garmin_schedule_id", sa.BigInteger(), nullable=True))
    for name, length in (("garmin_status", 16), ("garmin_error", 255), ("garmin_hash", 16)):
        op.add_column(
            "planned_session",
            sa.Column(name, sqlmodel.sql.sqltypes.AutoString(length=length), server_default="", nullable=False),
        )
    op.add_column("planned_session", sa.Column("garmin_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "user_settings", sa.Column("garmin_workouts_auto", sa.Boolean(), server_default=sa.false(), nullable=False)
    )


def downgrade() -> None:
    op.drop_column("user_settings", "garmin_workouts_auto")
    for name in ("garmin_sent_at", "garmin_hash", "garmin_error", "garmin_status", "garmin_schedule_id",
                 "garmin_workout_id"):  # fmt: skip
        op.drop_column("planned_session", name)
