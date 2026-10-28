"""Lectura de capturas de las fichas (listing-evidence-v1): tabla de evidencia (additive)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "listing_evidence",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "listing_id",
            UUID(as_uuid=True),
            sa.ForeignKey("marketplace_listings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("schema_version", sa.String(40), nullable=False),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("extraction_state", sa.String(20), nullable=False),
        sa.Column("failure_reason", sa.String(60)),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("image_count_total", sa.Integer, nullable=False),
        sa.Column("image_count_processed", sa.Integer, nullable=False),
        sa.Column("image_hashes", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("model_evidence", JSONB),
        sa.Column("derived", JSONB),
        sa.Column("evidence_grade", sa.String(1)),
        sa.Column("income_level", sa.String(2)),
        sa.Column("observed_monthly_income_usd", sa.Numeric(14, 2)),
        sa.Column("rpm_usd", sa.Numeric(10, 4)),
        sa.Column("rpm_sample_eligible", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("cost_usd", sa.Numeric(12, 6)),
        sa.Column("retain_until", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "extraction_state IN ('complete', 'no_images', 'failed')", name="evidence_state"
        ),
        sa.CheckConstraint(
            "evidence_grade IS NULL OR evidence_grade IN ('A', 'B', 'C', 'D', 'E', 'X')",
            name="evidence_grade",
        ),
    )
    op.create_index("ix_listing_evidence_listing_id", "listing_evidence", ["listing_id"])
    op.create_index("ix_listing_evidence_grade", "listing_evidence", ["evidence_grade"])


def downgrade() -> None:
    op.drop_index("ix_listing_evidence_grade", table_name="listing_evidence")
    op.drop_index("ix_listing_evidence_listing_id", table_name="listing_evidence")
    op.drop_table("listing_evidence")
