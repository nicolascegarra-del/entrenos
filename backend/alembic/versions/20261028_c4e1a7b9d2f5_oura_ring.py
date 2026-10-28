"""anillo Oura: conexión, webhooks, series diarias, sesiones, etiquetas, modo descanso y fuentes por métrica

Revision ID: c4e1a7b9d2f5
Revises: e6a1c4b8d2f0
Create Date: 2026-10-28 10:00:00.000000

Migración de datos: cada `daily_metric` existente pasa a guardar sus valores por fuente en
`raw["_sources"]` y la fuente de cada clave en `metric_sources` (ver `services/daily_sources`):

- Fila con raw de Garmin (alguna clave de nivel superior) → `garmin`, salvo `hrv_sdnn` (solo la da Apple) → `apple`.
- Fila sin raw: si tiene `resting_hr` o `hrv_sdnn` → `apple` (Health Connect no los da); si no, `health_connect`
  si la persona tiene token de Health Connect y nunca importó Apple Salud; si no, `apple`.
- `lt_speed` / `lt_hr` (umbral de Garmin guardado aparte) quedan sin fuente: se conservan tal cual.
Las claves que Apple rellenó en días de Garmin no se pueden distinguir y quedan como de Garmin.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4e1a7b9d2f5"
down_revision: str | None = "e6a1c4b8d2f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("now()")
JSONB = postgresql.JSONB(astext_type=sa.Text())
EMPTY = sa.text("'{}'")
WITHOUT_SOURCE = {"lt_speed", "lt_hr"}
APPLE_ONLY = {"hrv_sdnn"}
SOURCES = {"garmin", "coros", "health_connect", "apple", "oura"}


def infer_sources(metrics: dict, raw: dict, has_hc: bool, has_apple: bool) -> tuple[dict, dict]:
    """(`raw["_sources"]`, `metric_sources`) deducidos para una fila antigua."""
    garmin_raw = any(not k.startswith("_") and k not in SOURCES for k in raw or {})
    if garmin_raw:
        default = "garmin"
    elif set(metrics) & {"resting_hr", "hrv_sdnn"}:
        default = "apple"
    else:
        default = "health_connect" if has_hc and not has_apple else "apple"
    by_source: dict[str, dict] = {}
    sources: dict[str, str] = {}
    for key, value in (metrics or {}).items():
        if key in WITHOUT_SOURCE or value is None:
            continue
        src = "apple" if key in APPLE_ONLY else default
        by_source.setdefault(src, {})[key] = value
        sources[key] = src
    return by_source, sources


def backfill(bind: sa.engine.Connection) -> int:
    """Marca las filas existentes con su fuente (idempotente: salta las que ya tienen `_sources`)."""
    hc = {r[0] for r in bind.execute(sa.text("SELECT user_id FROM ingest_token"))}
    apple = {r[0] for r in bind.execute(sa.text("SELECT DISTINCT user_id FROM apple_import"))}
    rows = bind.execute(sa.text("SELECT id, user_id, metrics, raw FROM daily_metric WHERE NOT (raw ? '_sources')"))
    update = sa.text("UPDATE daily_metric SET raw = :raw, metric_sources = :sources WHERE id = :id").bindparams(
        sa.bindparam("raw", type_=JSONB), sa.bindparam("sources", type_=JSONB)
    )
    count = 0
    for row_id, user_id, metrics, raw in rows.fetchall():
        by_source, sources = infer_sources(metrics or {}, raw or {}, user_id in hc, user_id in apple)
        bind.execute(update, {"raw": {**(raw or {}), "_sources": by_source}, "sources": sources, "id": row_id})
        count += 1
    return count


def upgrade() -> None:
    op.add_column("daily_metric", sa.Column("metric_sources", JSONB, server_default=EMPTY, nullable=False))
    op.add_column(
        "user_settings", sa.Column("recovery_source", sa.String(length=8), server_default="auto", nullable=False)
    )
    op.create_table(
        "oura_connection",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("oura_user_id", sa.String(length=64), nullable=False),
        sa.Column("access_token_enc", sa.Text(), nullable=False),
        sa.Column("refresh_token_enc", sa.Text(), server_default="", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("last_error", sa.String(length=255), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("history_status", sa.String(length=16), nullable=False),
        sa.Column("history_from", sa.Date(), nullable=True),
        sa.Column("history_to", sa.Date(), nullable=True),
        sa.Column("ring", JSONB, server_default=EMPTY, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(op.f("ix_oura_connection_oura_user_id"), "oura_connection", ["oura_user_id"], unique=False)
    op.create_table(
        "oura_webhook_subscription",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("remote_id", sa.String(length=64), nullable=False),
        sa.Column("data_type", sa.String(length=40), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("callback_url", sa.String(length=500), nullable=False),
        sa.Column("expiration_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("data_type", "event_type", "callback_url"),
        sa.UniqueConstraint("remote_id"),
    )
    op.create_table(
        "daily_series",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("data", JSONB, server_default=EMPTY, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "day", "source", "kind"),
    )
    op.create_index(op.f("ix_daily_series_user_id"), "daily_series", ["user_id"], unique=False)
    op.create_index(op.f("ix_daily_series_day"), "daily_series", ["day"], unique=False)
    op.create_table(
        "wellness_session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("external_id", sa.String(length=120), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mood", sa.String(length=16), nullable=True),
        sa.Column("hr_avg", sa.Float(), nullable=True),
        sa.Column("hrv_avg", sa.Float(), nullable=True),
        sa.Column("raw", JSONB, server_default=EMPTY, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "source", "external_id"),
    )
    op.create_index(op.f("ix_wellness_session_user_id"), "wellness_session", ["user_id"], unique=False)
    op.create_table(
        "health_tag",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("external_id", sa.String(length=120), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("comment", sa.String(length=500), nullable=False),
        sa.Column("raw", JSONB, server_default=EMPTY, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "source", "external_id"),
    )
    op.create_index(op.f("ix_health_tag_user_id"), "health_tag", ["user_id"], unique=False)
    op.create_index(op.f("ix_health_tag_day"), "health_tag", ["day"], unique=False)
    op.create_table(
        "rest_period",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("external_id", sa.String(length=120), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("raw", JSONB, server_default=EMPTY, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "source", "external_id"),
    )
    op.create_index(op.f("ix_rest_period_user_id"), "rest_period", ["user_id"], unique=False)
    backfill(op.get_bind())


def downgrade() -> None:
    op.drop_index(op.f("ix_rest_period_user_id"), table_name="rest_period")
    op.drop_table("rest_period")
    op.drop_index(op.f("ix_health_tag_day"), table_name="health_tag")
    op.drop_index(op.f("ix_health_tag_user_id"), table_name="health_tag")
    op.drop_table("health_tag")
    op.drop_index(op.f("ix_wellness_session_user_id"), table_name="wellness_session")
    op.drop_table("wellness_session")
    op.drop_index(op.f("ix_daily_series_day"), table_name="daily_series")
    op.drop_index(op.f("ix_daily_series_user_id"), table_name="daily_series")
    op.drop_table("daily_series")
    op.drop_table("oura_webhook_subscription")
    op.drop_index(op.f("ix_oura_connection_oura_user_id"), table_name="oura_connection")
    op.drop_table("oura_connection")
    op.drop_column("user_settings", "recovery_source")
    # Se quitan las marcas de fuente y el raw de Oura (los valores ya combinados se quedan en `metrics`).
    op.execute("UPDATE daily_metric SET raw = raw - '_sources' - 'oura'")
    op.drop_column("daily_metric", "metric_sources")
