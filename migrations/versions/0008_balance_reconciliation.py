"""Preserve observed dates, refresh state and retained balance reconciliation evidence."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "credit_balances",
        sa.Column("refresh_required", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "credit_balances",
        sa.Column("unit", sa.String(50), nullable=False, server_default="vidiq_credit"),
    )
    op.add_column(
        "credit_balances",
        sa.Column("confirmed_usage", sa.Numeric(18, 6), nullable=False, server_default="0"),
    )
    op.add_column("credit_balances", sa.Column("retain_until", sa.DateTime(timezone=True)))
    # Legacy observations have no source TTL. Bound them conservatively and require refresh.
    op.execute("UPDATE credit_balances SET retain_until = observed_at + interval '7 days'")
    op.add_column(
        "credit_balances",
        sa.Column(
            "source_observation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("raw_observations.id", ondelete="CASCADE"),
        ),
    )
    op.create_table(
        "balance_reconciliations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("auth_scope", sa.String(120), nullable=False),
        sa.Column("unit", sa.String(50), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retain_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("balance_change", sa.Numeric(18, 6)),
        sa.Column("radar_consumption", sa.Numeric(18, 6)),
        sa.Column("unattributed_change", sa.Numeric(18, 6)),
        sa.Column(
            "source_observation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("raw_observations.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "previous_observation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("raw_observations.id", ondelete="CASCADE"),
        ),
    )


def downgrade() -> None:
    op.drop_table("balance_reconciliations")
    for name in (
        "source_observation_id",
        "retain_until",
        "confirmed_usage",
        "unit",
        "refresh_required",
    ):
        op.drop_column("credit_balances", name)
