"""Initial evidence, discovery, review and resource schema.

Uses the frozen snapshot, never mutable application metadata. Later revisions must
not edit schema_v1. No provider content or credentials are seeded by a migration.
"""

from alembic import op

from nicheradar.repositories.schema_v1 import metadata

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata.create_all(bind=op.get_bind(), checkfirst=False)


def downgrade() -> None:
    metadata.drop_all(bind=op.get_bind(), checkfirst=False)
