"""coros oficial (oauth del mcp) y envío de entrenos

Revision ID: f2b6c8d4a1e3
Revises: e1f4a7b2c9d6
Create Date: 2026-10-24 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "f2b6c8d4a1e3"
down_revision: str | None = "e1f4a7b2c9d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = sqlmodel.sql.sqltypes.AutoString
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "oauth_client",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", S(length=32), nullable=False),
        sa.Column("issuer", S(length=255), nullable=False),
        sa.Column("redirect_uri", S(length=500), nullable=False),
        sa.Column("client_id", S(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "redirect_uri"),
    )
    op.create_table(
        "oauth_state",
        sa.Column("state", S(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", S(length=32), nullable=False),
        sa.Column("code_verifier", S(length=128), nullable=False),
        sa.Column("redirect_uri", S(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("state"),
    )
    op.create_index(op.f("ix_oauth_state_user_id"), "oauth_state", ["user_id"], unique=False)
    op.create_table(
        "coros_oauth",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("client_id", S(length=255), nullable=False),
        sa.Column("issuer", S(length=255), nullable=False),
        sa.Column("mcp_url", S(length=255), nullable=False),
        sa.Column("access_token_enc", sa.Text(), nullable=False),
        sa.Column("refresh_token_enc", sa.Text(), server_default="", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", S(length=16), nullable=False),
        sa.Column("last_error", S(length=255), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.add_column("planned_session", sa.Column("coros_day", sa.Date(), nullable=True))
    for name, length in (("coros_id_in_plan", 64), ("coros_status", 16), ("coros_error", 255), ("coros_hash", 16)):
        op.add_column("planned_session", sa.Column(name, S(length=length), server_default="", nullable=False))
    op.add_column("planned_session", sa.Column("coros_sent_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for name in ("coros_sent_at", "coros_hash", "coros_error", "coros_status", "coros_id_in_plan", "coros_day"):
        op.drop_column("planned_session", name)
    op.drop_table("coros_oauth")
    op.drop_index(op.f("ix_oauth_state_user_id"), table_name="oauth_state")
    op.drop_table("oauth_state")
    op.drop_table("oauth_client")
