"""Enriquecimiento de fichas con la API de YouTube: tabla de instantáneas de canal (additive)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "listing_channel_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "listing_id",
            UUID(as_uuid=True),
            sa.ForeignKey("marketplace_listings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("youtube_channel_id", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(200)),
        sa.Column("country", sa.String(2)),
        sa.Column("channel_created_at", sa.DateTime(timezone=True)),
        sa.Column("subscribers", sa.BigInteger),
        sa.Column("total_views", sa.BigInteger),
        sa.Column("video_count", sa.BigInteger),
        sa.Column("recent_videos", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("retain_until", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('ok', 'not_found')", name="channel_snapshot_status"),
    )
    op.create_index(
        "ix_listing_channel_snapshots_listing_id", "listing_channel_snapshots", ["listing_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_listing_channel_snapshots_listing_id", table_name="listing_channel_snapshots")
    op.drop_table("listing_channel_snapshots")
