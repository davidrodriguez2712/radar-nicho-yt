"""Solicitudes de propuesta de subnicho para la API (additive)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def _ts(name: str, nullable: bool = True) -> sa.Column[object]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "subniche_proposal_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("idempotency_key", sa.String(100), nullable=False, unique=True),
        sa.Column("input_text", sa.String(500), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("manual", JSONB),
        sa.Column("origin", sa.String(12), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(10), nullable=False, server_default="queued"),
        sa.Column("error_code", sa.String(80)),
        sa.Column("hypothesis_slug", sa.String(60)),
        _ts("created_at", nullable=False),
        _ts("started_at"),
        _ts("finished_at"),
        sa.CheckConstraint("kind IN ('query', 'video', 'channel')", name="proposal_kind"),
        sa.CheckConstraint(
            "origin IN ('manual', 'catalog', 'marketplace', 'lead')", name="proposal_origin"
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'ready', 'failed')", name="proposal_status"
        ),
    )
    op.create_index(
        "ix_subniche_proposal_status_created",
        "subniche_proposal_requests",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_subniche_proposal_status_created", table_name="subniche_proposal_requests")
    op.drop_table("subniche_proposal_requests")
