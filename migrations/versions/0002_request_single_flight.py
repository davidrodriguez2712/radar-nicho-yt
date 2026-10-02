"""Prevent two unresolved paid requests for the same cache/account scope."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_provider_requests_unresolved",
        "provider_requests",
        ["provider", "auth_scope", "cache_key"],
        unique=True,
        postgresql_where=sa.text("state IN ('prepared', 'sent', 'unknown_charge')"),
    )


def downgrade() -> None:
    op.drop_index("uq_provider_requests_unresolved", table_name="provider_requests")
