"""Flow research: the language joins the key of a request (additive, closes language-less work)."""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

ACTIVE = "status IN ('pendiente', 'en_curso')"
REJECTION = (
    '{"problems": [{"path": "language", "message": '
    '"el encargo se creó antes de elegir idioma: vuelve a iniciarlo con uno"}]}'
)


def upgrade() -> None:
    for table in ("flow_research_requests", "flow_research_dossiers"):
        op.add_column(
            table, sa.Column("language", sa.String(10), nullable=False, server_default="unknown")
        )
    # An active request without a language would research the wrong market: close it, never guess.
    op.execute(
        sa.text(
            "UPDATE flow_research_requests SET status = 'rechazado', lease_owner = NULL, "
            "lease_until = NULL, rejection = CAST(:rejection AS jsonb), updated_at = now() "
            f"WHERE {ACTIVE} AND language = 'unknown'"
        ).bindparams(rejection=REJECTION)
    )
    op.drop_index("uq_flow_research_active", table_name="flow_research_requests")
    op.create_index(
        "uq_flow_research_active",
        "flow_research_requests",
        ["niche_label", "format", "language"],
        unique=True,
        postgresql_where=sa.text(ACTIVE),
    )
    op.drop_index("ix_flow_research_dossiers_lookup", table_name="flow_research_dossiers")
    op.create_index(
        "ix_flow_research_dossiers_lookup",
        "flow_research_dossiers",
        ["niche_label", "format", "language", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_flow_research_dossiers_lookup", table_name="flow_research_dossiers")
    op.create_index(
        "ix_flow_research_dossiers_lookup",
        "flow_research_dossiers",
        ["niche_label", "format", "created_at"],
    )
    op.drop_index("uq_flow_research_active", table_name="flow_research_requests")
    # Two active requests that differ only by language cannot coexist under the old key.
    op.execute(
        sa.text(
            "UPDATE flow_research_requests SET status = 'rechazado', lease_owner = NULL, "
            "lease_until = NULL, updated_at = now() WHERE id IN ("
            "SELECT id FROM (SELECT id, row_number() OVER (PARTITION BY niche_label, format "
            f"ORDER BY created_at) AS n FROM flow_research_requests WHERE {ACTIVE}) ranked "
            "WHERE n > 1)"
        )
    )
    op.create_index(
        "uq_flow_research_active",
        "flow_research_requests",
        ["niche_label", "format"],
        unique=True,
        postgresql_where=sa.text(ACTIVE),
    )
    for table in ("flow_research_dossiers", "flow_research_requests"):
        op.drop_column(table, "language")
