"""Versioned default production recipes per format; auto-applied, no invented figures."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "production_recipe_defaults",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id", UUID(as_uuid=True), sa.ForeignKey("creator_profiles.id"), nullable=False
        ),
        sa.Column("format", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("configuration", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "profile_id", "format", "version", name="uq_production_recipe_default_version"
        ),
        sa.CheckConstraint("version > 0", name="recipe_default_version"),
        sa.CheckConstraint("format IN ('long', 'shorts')", name="recipe_default_format"),
    )


def downgrade() -> None:
    op.drop_table("production_recipe_defaults")
