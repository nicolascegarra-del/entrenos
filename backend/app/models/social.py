"""
Parte social: perfil público, seguir (con aprobación), bloqueos, kudos, comentarios y duelos 1 contra 1.

Todo cae en cascada con la cuenta o la actividad. La autorización (quién ve qué) está centralizada en
`services/social.py`: los modelos solo guardan datos.
"""

from datetime import date, datetime

from sqlalchemy import Column, DateTime, Index, UniqueConstraint, event, select
from sqlmodel import Field, SQLModel

from app.models.activity import Activity
from app.models.base import created_at_field


class SocialProfile(SQLModel, table=True):
    """Perfil para la parte social. Sin perfil, la persona no aparece en búsquedas ni clasificaciones."""

    __tablename__ = "social_profile"

    user_id: int = Field(foreign_key="user.id", primary_key=True, ondelete="CASCADE")
    display_name: str = Field(max_length=60)
    handle: str = Field(max_length=30, unique=True, index=True)  # minúsculas, [a-z0-9_.]
    bio: str = Field(default="", max_length=200)
    visibility: str = Field(default="private", max_length=8)  # private | public
    default_activity_visibility: str = Field(default="followers", max_length=10)  # followers | private
    hide_map_ends_m: int = Field(default=300, ge=0, le=1000)
    show_pace: bool = True
    show_maps: bool = True
    created_at: datetime = created_at_field()


class Follow(SQLModel, table=True):
    """`follower_id` sigue a `followee_id`. Pendiente hasta que la otra persona acepta (perfil privado)."""

    __tablename__ = "follow"
    __table_args__ = (
        UniqueConstraint("follower_id", "followee_id"),
        Index("ix_follow_followee_status", "followee_id", "status"),
        Index("ix_follow_follower_status", "follower_id", "status"),
    )

    id: int | None = Field(default=None, primary_key=True)
    follower_id: int = Field(foreign_key="user.id", ondelete="CASCADE")
    followee_id: int = Field(foreign_key="user.id", ondelete="CASCADE")
    status: str = Field(default="pending", max_length=8)  # pending | accepted
    created_at: datetime = created_at_field()
    accepted_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class Block(SQLModel, table=True):
    """`blocker_id` bloquea a `blocked_id`: se ocultan el uno al otro en todo."""

    __tablename__ = "block"
    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id"),)

    id: int | None = Field(default=None, primary_key=True)
    blocker_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    blocked_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    created_at: datetime = created_at_field()


class Kudos(SQLModel, table=True):
    __tablename__ = "kudos"
    __table_args__ = (UniqueConstraint("activity_id", "user_id"),)

    id: int | None = Field(default=None, primary_key=True)
    activity_id: int = Field(foreign_key="activity.id", index=True, ondelete="CASCADE")
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    created_at: datetime = created_at_field()


class ActivityComment(SQLModel, table=True):
    """Comentario en una actividad. Se borra de forma lógica (`deleted_at`)."""

    __tablename__ = "activity_comment"

    id: int | None = Field(default=None, primary_key=True)
    activity_id: int = Field(foreign_key="activity.id", index=True, ondelete="CASCADE")
    author_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    body: str = Field(max_length=500)
    created_at: datetime = created_at_field()
    deleted_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class Duel(SQLModel, table=True):
    """
    Duelo 1 contra 1 entre `start_date` y `end_date` (incluidos, días de Madrid). Mientras está
    pendiente, las fechas son provisionales: al aceptar empieza ese día. Al cerrarse se guardan los
    marcadores finales (`challenger_value`/`opponent_value`) para no recalcular el historial.
    """

    __tablename__ = "duel"

    id: int | None = Field(default=None, primary_key=True)
    challenger_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    opponent_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    metric: str = Field(max_length=12)  # km | time | elevation | days | best_5k | best_10k
    sport: str = Field(default="all", max_length=10)  # all | running | cycling
    duration: str = Field(default="1w", max_length=4)  # 1w | 2w | 1m
    start_date: date
    end_date: date
    status: str = Field(default="pending", max_length=10, index=True)
    winner_id: int | None = Field(default=None, foreign_key="user.id", ondelete="SET NULL")
    last_leader_id: int | None = Field(default=None, foreign_key="user.id", ondelete="SET NULL")
    challenger_value: float | None = None
    opponent_value: float | None = None
    created_at: datetime = created_at_field()


@event.listens_for(Activity, "before_insert")
def _default_visibility(_mapper, connection, target: Activity) -> None:
    """Las actividades nuevas toman la visibilidad por defecto del perfil social (sin perfil, «Solo yo»)."""
    if target.visibility in ("followers", "private"):
        return
    value = connection.execute(
        select(SocialProfile.default_activity_visibility).where(SocialProfile.user_id == target.user_id)
    ).scalar()
    target.visibility = value if value in ("followers", "private") else "private"
