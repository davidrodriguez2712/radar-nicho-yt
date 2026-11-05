"""Lecturas de tweets de X e imágenes compartidas, y su vínculo con las propuestas (additive)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def _ts(name: str, nullable: bool = True) -> sa.Column[object]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "lead_read_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("idempotency_key", sa.String(100), nullable=False, unique=True),
        sa.Column("kind", sa.String(6), nullable=False),
        sa.Column("tweet_id", sa.String(20)),
        sa.Column("tweet_author", sa.String(15)),
        sa.Column("status", sa.String(10), nullable=False, server_default="queued"),
        sa.Column("stage", sa.String(10)),
        sa.Column("error_code", sa.String(80)),
        sa.Column("untrusted_text", sa.String(1000)),
        sa.Column("image_data", sa.LargeBinary),
        sa.Column("image_type", sa.String(10)),
        sa.Column("photos_read", sa.SmallInteger, nullable=False, server_default="0"),
        _ts("created_at", nullable=False),
        _ts("started_at"),
        _ts("finished_at"),
        _ts("closed_at"),
        sa.CheckConstraint("kind IN ('tweet', 'image')", name="lead_read_kind"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'ready', 'failed')", name="lead_read_status"
        ),
        sa.CheckConstraint(
            "stage IS NULL OR stage IN ('text', 'images', 'mentions', 'resolving')",
            name="lead_read_stage",
        ),
        sa.CheckConstraint(
            "image_type IS NULL OR image_type IN ('image/png', 'image/jpeg', 'image/webp')",
            name="lead_read_image_type",
        ),
        sa.CheckConstraint("photos_read BETWEEN 0 AND 4", name="lead_read_photos"),
        sa.CheckConstraint("(kind = 'tweet') = (tweet_id IS NOT NULL)", name="lead_read_tweet_id"),
        sa.CheckConstraint("image_data IS NULL OR kind = 'image'", name="lead_read_image_kind"),
        sa.CheckConstraint(
            "image_data IS NULL OR octet_length(image_data) <= 5242880", name="lead_read_image_size"
        ),
    )
    op.create_index("ix_lead_read_status_created", "lead_read_requests", ["status", "created_at"])
    op.create_table(
        "lead_candidates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "read_id",
            UUID(as_uuid=True),
            sa.ForeignKey("lead_read_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.SmallInteger, nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("value", sa.String(120), nullable=False),
        sa.Column("found_in", sa.String(5), nullable=False),
        sa.Column("resolution", sa.String(12), nullable=False),
        sa.Column("channel_id", sa.String(24)),
        sa.Column("channel_title", sa.String(120)),
        sa.Column("subscribers", sa.BigInteger),
        sa.Column(
            "proposal_request_id",
            UUID(as_uuid=True),
            sa.ForeignKey("subniche_proposal_requests.id", ondelete="SET NULL"),
        ),
        _ts("created_at", nullable=False),
        _ts("updated_at", nullable=False),
        sa.CheckConstraint("position BETWEEN 0 AND 9", name="lead_candidate_position"),
        sa.CheckConstraint(
            "kind IN ('handle', 'channel_id', 'video', 'name')", name="lead_candidate_kind"
        ),
        sa.CheckConstraint("found_in IN ('text', 'image', 'both')", name="lead_candidate_found"),
        sa.CheckConstraint(
            "resolution IN ('resolved', 'name_only', 'name_queued', 'searching', 'ambiguous', "
            "'not_found')",
            name="lead_candidate_resolution",
        ),
        sa.CheckConstraint(
            "resolution NOT IN ('resolved', 'ambiguous') OR channel_id IS NOT NULL",
            name="lead_candidate_channel",
        ),
        sa.UniqueConstraint("read_id", "kind", "value", name="uq_lead_candidate_mention"),
        sa.UniqueConstraint("read_id", "position", name="uq_lead_candidate_position"),
    )
    op.add_column("subniche_proposal_requests", sa.Column("lead_author", sa.String(15)))
    op.add_column("subniche_proposal_requests", sa.Column("lead_tweet_id", sa.String(20)))


def downgrade() -> None:
    op.drop_column("subniche_proposal_requests", "lead_tweet_id")
    op.drop_column("subniche_proposal_requests", "lead_author")
    op.drop_table("lead_candidates")
    op.drop_index("ix_lead_read_status_created", table_name="lead_read_requests")
    op.drop_table("lead_read_requests")
