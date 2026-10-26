"""Pilotos: tabla propia de mediciones de Shorts, channel-report-v2 (additive)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

PERCENTAGES = (
    "engaged_view_ratio_pct",
    "avg_view_pct",
    "shorts_feed_share_pct",
    "stayed_to_watch_pct",
    "early_retention_pct",
)


def upgrade() -> None:
    op.create_table(
        "pilot_shorts_measurements",
        sa.Column(
            "pilot_video_id",
            UUID(as_uuid=True),
            sa.ForeignKey("pilot_videos.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("engaged_views", sa.Integer, nullable=False),
        *(sa.Column(name, sa.Numeric(5, 2)) for name in PERCENTAGES),
        sa.Column("shares", sa.Integer),
        sa.Column("early_retention_second", sa.Numeric(5, 2)),
        sa.CheckConstraint("engaged_views >= 0", name="pilot_shorts_engaged_views"),
        sa.CheckConstraint("shares IS NULL OR shares >= 0", name="pilot_shorts_shares"),
        sa.CheckConstraint(
            "early_retention_second IS NULL OR early_retention_second BETWEEN 0 AND 180",
            name="pilot_shorts_early_second",
        ),
        sa.CheckConstraint(
            "(early_retention_pct IS NULL) = (early_retention_second IS NULL)",
            name="pilot_shorts_early_pair",
        ),
        *(
            sa.CheckConstraint(
                f"{name} IS NULL OR {name} BETWEEN 0 AND 100", name=f"pilot_shorts_{name}"
            )
            for name in PERCENTAGES
        ),
    )


def downgrade() -> None:
    op.drop_table("pilot_shorts_measurements")
