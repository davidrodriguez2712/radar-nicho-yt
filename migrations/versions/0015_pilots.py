"""Pilotos de canal: paquetes, reportes de videos, bitácora y tokens por canal (additive)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

STATES = "('autorizado', 'entregado', 'en_ejecucion', 'decision_pendiente', 'cerrado', 'cancelado')"
OPEN = "status NOT IN ('cerrado', 'cancelado') AND target_channel IS NOT NULL"


def _tz(name: str, *, nullable: bool = True) -> sa.Column[object]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "pilots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("pilot_id", sa.String(60), nullable=False, unique=True),
        sa.Column("niche_label", sa.String(140), nullable=False),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("language", sa.String(10), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("target_channel", sa.String(60)),
        sa.Column("package", JSONB, nullable=False),
        sa.Column("package_sha256", sa.String(64), nullable=False),
        sa.Column("authorized_by", sa.String(160), nullable=False),
        _tz("authorized_at", nullable=False),
        _tz("valid_until", nullable=False),
        _tz("delivered_at"),
        _tz("first_report_at"),
        _tz("last_report_at"),
        sa.Column("acknowledged", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("evaluation", JSONB),
        _tz("closed_at"),
        sa.Column("close_reason", sa.Text),
        sa.Column("channel_info", JSONB),
        _tz("created_at", nullable=False),
        _tz("updated_at", nullable=False),
        sa.CheckConstraint(f"status IN {STATES}", name="pilots_status"),
        sa.CheckConstraint("format IN ('long', 'shorts')", name="pilots_format"),
    )
    op.create_index(
        "uq_pilots_open_channel",
        "pilots",
        ["target_channel"],
        unique=True,
        postgresql_where=sa.text(OPEN),
    )
    op.create_index("ix_pilots_status", "pilots", ["status", "created_at"])
    op.create_table(
        "pilot_videos",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "pilot_pk",
            UUID(as_uuid=True),
            sa.ForeignKey("pilots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("video_id", sa.String(60), nullable=False),
        sa.Column("source_state", sa.String(40), nullable=False),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("visibility", sa.String(10), nullable=False),
        _tz("published_at"),
        sa.Column("cost_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("cost_equivalent_usd", sa.Numeric(12, 2)),
        sa.Column("machine_minutes", sa.Integer),
        sa.Column("failure_code", sa.String(60)),
        _tz("measured_at"),
        sa.Column("window_days", sa.Integer),
        sa.Column("avd_pct", sa.Numeric(5, 2)),
        sa.Column("views", sa.Integer),
        sa.Column("browse_share_pct", sa.Numeric(5, 2)),
        sa.Column("subscribers_gained", sa.Integer),
        _tz("reported_at", nullable=False),
        sa.UniqueConstraint("pilot_pk", "video_id", name="uq_pilot_videos_key"),
    )
    op.create_table(
        "pilot_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("seq", sa.BigInteger, sa.Identity(), nullable=False),
        sa.Column(
            "pilot_pk",
            UUID(as_uuid=True),
            sa.ForeignKey("pilots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        _tz("at", nullable=False),
        sa.Column("actor", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("detail", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_pilot_events_pilot", "pilot_events", ["pilot_pk", "at"])
    op.create_table(
        "channel_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("channel_id", sa.String(60), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("label", sa.String(80), nullable=False),
        _tz("created_at", nullable=False),
        _tz("last_used_at"),
        _tz("revoked_at"),
    )
    op.create_index("ix_channel_tokens_channel", "channel_tokens", ["channel_id"])


def downgrade() -> None:
    op.drop_table("channel_tokens")
    op.drop_table("pilot_events")
    op.drop_table("pilot_videos")
    op.drop_table("pilots")
