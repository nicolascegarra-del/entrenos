"""amigos: perfil social, seguir, bloqueos, kudos, comentarios, duelos y visibilidad de actividades

Todas las actividades existentes quedan en «Solo yo» (private): solo se comparte lo que llegue
después de crear el perfil social, salvo que la persona elija compartir también su historial.

Revision ID: a1c5e9d3b7f2
Revises: a9d4f6b2c8e1
Create Date: 2026-11-13 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "a1c5e9d3b7f2"
down_revision: str | None = "a9d4f6b2c8e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = sqlmodel.sql.sqltypes.AutoString
NOW = sa.text("now()")


def _user_fk(column: str, ondelete: str = "CASCADE") -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([column], ["user.id"], ondelete=ondelete)


def upgrade() -> None:
    # Las existentes se crean con el valor por defecto «private» (Solo yo).
    op.add_column("activity", sa.Column("visibility", sa.String(length=10), server_default="private", nullable=False))
    op.add_column("notification_prefs", sa.Column("social", sa.Boolean(), server_default=sa.true(), nullable=False))

    op.create_table(
        "social_profile",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("display_name", S(length=60), nullable=False),
        sa.Column("handle", S(length=30), nullable=False),
        sa.Column("bio", S(length=200), nullable=False),
        sa.Column("visibility", S(length=8), nullable=False),
        sa.Column("default_activity_visibility", S(length=10), nullable=False),
        sa.Column("hide_map_ends_m", sa.Integer(), nullable=False),
        sa.Column("show_pace", sa.Boolean(), nullable=False),
        sa.Column("show_maps", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        _user_fk("user_id"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(op.f("ix_social_profile_handle"), "social_profile", ["handle"], unique=True)

    op.create_table(
        "follow",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("follower_id", sa.Integer(), nullable=False),
        sa.Column("followee_id", sa.Integer(), nullable=False),
        sa.Column("status", S(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        _user_fk("follower_id"),
        _user_fk("followee_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("follower_id", "followee_id"),
    )
    op.create_index("ix_follow_followee_status", "follow", ["followee_id", "status"], unique=False)
    op.create_index("ix_follow_follower_status", "follow", ["follower_id", "status"], unique=False)

    op.create_table(
        "block",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("blocker_id", sa.Integer(), nullable=False),
        sa.Column("blocked_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        _user_fk("blocker_id"),
        _user_fk("blocked_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("blocker_id", "blocked_id"),
    )
    op.create_index(op.f("ix_block_blocker_id"), "block", ["blocker_id"], unique=False)
    op.create_index(op.f("ix_block_blocked_id"), "block", ["blocked_id"], unique=False)

    op.create_table(
        "kudos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["activity_id"], ["activity.id"], ondelete="CASCADE"),
        _user_fk("user_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("activity_id", "user_id"),
    )
    op.create_index(op.f("ix_kudos_activity_id"), "kudos", ["activity_id"], unique=False)
    op.create_index(op.f("ix_kudos_user_id"), "kudos", ["user_id"], unique=False)

    op.create_table(
        "activity_comment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column("body", S(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["activity_id"], ["activity.id"], ondelete="CASCADE"),
        _user_fk("author_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_activity_comment_activity_id"), "activity_comment", ["activity_id"], unique=False)
    op.create_index(op.f("ix_activity_comment_author_id"), "activity_comment", ["author_id"], unique=False)

    op.create_table(
        "duel",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("challenger_id", sa.Integer(), nullable=False),
        sa.Column("opponent_id", sa.Integer(), nullable=False),
        sa.Column("metric", S(length=12), nullable=False),
        sa.Column("sport", S(length=10), nullable=False),
        sa.Column("duration", S(length=4), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", S(length=10), nullable=False),
        sa.Column("winner_id", sa.Integer(), nullable=True),
        sa.Column("last_leader_id", sa.Integer(), nullable=True),
        sa.Column("challenger_value", sa.Float(), nullable=True),
        sa.Column("opponent_value", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        _user_fk("challenger_id"),
        _user_fk("opponent_id"),
        _user_fk("winner_id", "SET NULL"),
        _user_fk("last_leader_id", "SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_duel_challenger_id"), "duel", ["challenger_id"], unique=False)
    op.create_index(op.f("ix_duel_opponent_id"), "duel", ["opponent_id"], unique=False)
    op.create_index(op.f("ix_duel_status"), "duel", ["status"], unique=False)


def downgrade() -> None:
    op.drop_table("duel")
    op.drop_table("activity_comment")
    op.drop_table("kudos")
    op.drop_table("block")
    op.drop_table("follow")
    op.drop_table("social_profile")
    op.drop_column("notification_prefs", "social")
    op.drop_column("activity", "visibility")
