"""Persist scoped discovery and refresh continuation without copying provider text."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discovery_cursors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id", UUID(as_uuid=True), sa.ForeignKey("creator_profiles.id"), nullable=False
        ),
        sa.Column(
            "family_id", UUID(as_uuid=True), sa.ForeignKey("seed_families.id"), nullable=False
        ),
        sa.Column("opportunity_id", UUID(as_uuid=True), sa.ForeignKey("opportunities.id")),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("work_key", sa.String(120), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("pending_job_id", UUID(as_uuid=True), sa.ForeignKey("jobs.id")),
        sa.UniqueConstraint("profile_id", "mode", "work_key", name="uq_discovery_cursor_scope"),
        sa.CheckConstraint("mode IN ('synthetic', 'live')", name="discovery_mode"),
    )


def downgrade() -> None:
    op.drop_table("discovery_cursors")
