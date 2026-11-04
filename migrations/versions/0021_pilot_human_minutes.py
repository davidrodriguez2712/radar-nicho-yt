"""Minutos humanos por video del piloto (additive)."""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

CONSTRAINT = "pilot_videos_human_minutes_nonneg"


def upgrade() -> None:
    op.add_column("pilot_videos", sa.Column("human_minutes", sa.Integer))
    op.add_column("pilot_videos", sa.Column("human_minutes_method", sa.String(60)))
    op.create_check_constraint(
        CONSTRAINT, "pilot_videos", "human_minutes IS NULL OR human_minutes >= 0"
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT, "pilot_videos", type_="check")
    op.drop_column("pilot_videos", "human_minutes_method")
    op.drop_column("pilot_videos", "human_minutes")
