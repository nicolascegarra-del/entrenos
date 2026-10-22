from datetime import date, datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field


class Achievement(SQLModel, table=True):
    """
    Logro conseguido (hito, racha, récord o reto del mes). `key` identifica el logro y no se repite
    por persona; `achieved_on` es el día real en que se consiguió (puede ser antiguo al calcular el
    historial por primera vez).
    """

    __tablename__ = "achievement"
    __table_args__ = (UniqueConstraint("user_id", "key"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    key: str = Field(max_length=80)
    kind: str = Field(max_length=16)  # milestone | streak | record | challenge
    title: str = Field(max_length=160)
    description: str = Field(default="", max_length=255)
    achieved_on: date
    activity_id: int | None = Field(default=None, foreign_key="activity.id", ondelete="SET NULL")
    created_at: datetime = created_at_field()
