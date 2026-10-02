"""Track every source of a derived topic artifact, not only its anchor."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "topic_artifact_sources",
        sa.Column(
            "artifact_id",
            UUID(as_uuid=True),
            sa.ForeignKey("topic_artifacts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "observation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("raw_observations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("topic_artifact_sources")
