"""entrenos de Oura completos: serie de FC, MET, FC mínima, zonas e intensidad

Los entrenos de Oura ya importados solo tenían FC media y máxima. Se vuelven a montar con lo que ya está
guardado (FC continua del anillo y MET del día): serie de FC y de MET, FC mín., tiempo en zonas… Solo
datos: sin cambios de esquema y sin llamar a Oura (la intensidad y la etiqueta llegan al volver a
sincronizar).

Revision ID: a9d4f6b2c8e1
Revises: f2c7d9a1b4e6
Create Date: 2026-10-31 20:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
from sqlmodel import Session

revision: str = "a9d4f6b2c8e1"
down_revision: str | None = "f2c7d9a1b4e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from app.services.oura_sync import reprocess_workouts

    with Session(bind=op.get_bind()) as session:
        reprocess_workouts(session)


def downgrade() -> None:
    # Las series y métricas nuevas se quedan: no estorban y la siguiente sincronización las vuelve a escribir.
    pass
