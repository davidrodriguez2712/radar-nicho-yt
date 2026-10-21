"""Flow research: requests handed to Claude Code and the dossiers it returns (additive)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

ACTIVE = "status IN ('pendiente', 'en_curso')"


def _tz(name: str, *, nullable: bool = True) -> sa.Column[object]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "flow_research_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("niche_label", sa.String(140), nullable=False),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("evidence", JSONB, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("lease_owner", sa.String(120)),
        _tz("lease_until"),
        sa.Column("rejection", JSONB),
        _tz("created_at", nullable=False),
        _tz("updated_at", nullable=False),
        _tz("retain_until", nullable=False),
        sa.CheckConstraint(
            "status IN ('pendiente', 'en_curso', 'listo', 'rechazado')",
            name="flow_research_status",
        ),
        sa.CheckConstraint("format IN ('long', 'shorts')", name="flow_research_format"),
    )
    op.create_index(
        "uq_flow_research_active",
        "flow_research_requests",
        ["niche_label", "format"],
        unique=True,
        postgresql_where=sa.text(ACTIVE),
    )
    op.create_index(
        "ix_flow_research_requests_status", "flow_research_requests", ["status", "created_at"]
    )
    op.create_table(
        "flow_research_dossiers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "request_id",
            UUID(as_uuid=True),
            sa.ForeignKey("flow_research_requests.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("niche_label", sa.String(140), nullable=False),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("schema_version", sa.String(20), nullable=False),
        sa.Column("content", JSONB, nullable=False),
        _tz("created_at", nullable=False),
        _tz("retain_until", nullable=False),
    )
    op.create_index(
        "ix_flow_research_dossiers_lookup",
        "flow_research_dossiers",
        ["niche_label", "format", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("flow_research_dossiers")
    op.drop_table("flow_research_requests")
