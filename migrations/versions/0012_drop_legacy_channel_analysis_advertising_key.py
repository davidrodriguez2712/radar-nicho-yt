"""Strip the legacy `channel_analysis_advertising` key from creator_profiles.configuration.

Commit 179d29c (2026-10-02) briefly added a `channel_analysis_advertising`
field to `CreatorProfile`. It was removed again by this plan's Task 7
(commit 4a97871), and `CreatorProfile` uses `model_config = ConfigDict(extra="forbid")`,
so any profile row persisted while that field existed (via `PUT /profile`,
`update_profile`, or `seed_profile`) now fails `CreatorProfile.model_validate`
on every `get_profile` call. The Postgres JSONB `-` operator is a no-op on a
missing key, so this UPDATE is safe to run unconditionally on every
environment, including ones that never had the stale key.
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE creator_profiles "
            "SET configuration = configuration - 'channel_analysis_advertising'"
        )
    )


def downgrade() -> None:
    # Irreversible data cleanup: the original (stale) key's value, if any, was
    # never meaningful application data, so there is nothing to restore.
    pass
