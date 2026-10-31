"""sincronización general para todas las conexiones: intervalos de 1, 4, 8, 16 y 24 h

Los intervalos antiguos (15, 30, 60, 120, 360, 720 y 1440 min) pasan al nuevo más cercano por arriba
(nunca a uno más frecuente salvo los de menos de 1 h, que pasan a 1 h). Por defecto, 4 h.

Revision ID: f2c7d9a1b4e6
Revises: e8b4c2a6d1f3
Create Date: 2026-10-31 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2c7d9a1b4e6"
down_revision: str | None = "e8b4c2a6d1f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE user_settings SET sync_interval_min = CASE "
            "WHEN sync_interval_min <= 60 THEN 60 WHEN sync_interval_min <= 240 THEN 240 "
            "WHEN sync_interval_min <= 480 THEN 480 WHEN sync_interval_min <= 960 THEN 960 ELSE 1440 END"
        )
    )


def downgrade() -> None:
    # Los valores nuevos también eran válidos o cercanos a los antiguos: no hace falta deshacer nada.
    pass
