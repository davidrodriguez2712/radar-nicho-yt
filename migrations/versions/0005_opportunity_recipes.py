"""Versioned manual production-plan assignments; no experiment or purchase state."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opportunity_recipe_assignments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id", UUID(as_uuid=True), sa.ForeignKey("opportunities.id"), nullable=False
        ),
        sa.Column(
            "profile_id", UUID(as_uuid=True), sa.ForeignKey("creator_profiles.id"), nullable=False
        ),
        sa.Column(
            "recipe_id", UUID(as_uuid=True), sa.ForeignKey("production_recipes.id"), nullable=False
        ),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "opportunity_id", "profile_id", "version", name="uq_opportunity_recipe_version"
        ),
        sa.CheckConstraint("version > 0", name="recipe_assignment_version"),
    )


def downgrade() -> None:
    op.drop_table("opportunity_recipe_assignments")
