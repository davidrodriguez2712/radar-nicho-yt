"""Retained manual advertising assumptions and frozen scoring references."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opportunity_scoring_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id", UUID(as_uuid=True), sa.ForeignKey("opportunities.id"), nullable=False
        ),
        sa.Column(
            "profile_id", UUID(as_uuid=True), sa.ForeignKey("creator_profiles.id"), nullable=False
        ),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("configuration", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retain_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expired_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "opportunity_id", "profile_id", "version", name="uq_opportunity_scoring_version"
        ),
        sa.CheckConstraint("version > 0", name="scoring_config_version"),
    )


def downgrade() -> None:
    op.drop_table("opportunity_scoring_configs")
