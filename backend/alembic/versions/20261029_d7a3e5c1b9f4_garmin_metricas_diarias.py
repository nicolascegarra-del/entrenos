"""vuelve a leer las métricas diarias de Garmin con los campos nuevos del catálogo

Estrés por niveles y máximo, Body Battery, SpO2, fases del sueño, minutos de intensidad, pisos, HRV de 7
días… Solo datos: sin cambios de esquema. Lee el raw ya guardado; no llama a Garmin.

Revision ID: d7a3e5c1b9f4
Revises: c4e1a7b9d2f5
Create Date: 2026-10-29 10:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
from sqlmodel import Session

revision: str = "d7a3e5c1b9f4"
down_revision: str | None = "c4e1a7b9d2f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from app.services.sync_service import reparse_garmin_daily

    with Session(bind=op.get_bind()) as session:
        reparse_garmin_daily(session)


def downgrade() -> None:
    # Los valores nuevos se quedan: no estorban y la siguiente sincronización los vuelve a escribir igual.
    pass
