"""Advertising benchmarks: real RPM ranges per niche, seeded once from packaged data."""

import json
from datetime import UTC, datetime
from importlib.resources import files
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

TABLE = sa.table(
    "advertising_benchmarks",
    sa.column("id"),
    sa.column("niche_label"),
    sa.column("niche_description"),
    sa.column("format"),
    sa.column("rate_low"),
    sa.column("rate_high"),
    sa.column("source"),
    sa.column("assumptions"),
    sa.column("created_at"),
)


def upgrade() -> None:
    op.create_table(
        "advertising_benchmarks",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("niche_label", sa.String(120), nullable=False, unique=True),
        sa.Column("niche_description", sa.Text, nullable=False),
        sa.Column("format", sa.String(20), nullable=False),
        sa.Column("rate_low", sa.Numeric, nullable=False),
        sa.Column("rate_high", sa.Numeric, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("assumptions", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("format IN ('long', 'shorts')", name="advertising_benchmark_format"),
        sa.CheckConstraint("rate_low <= rate_high", name="advertising_benchmark_rate_order"),
    )
    niches = json.loads(
        files("nicheradar.data").joinpath("youtube_niches_rpm_longform_2026.json").read_text()
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        TABLE,
        [
            {
                "id": uuid4(),
                "niche_label": n["niche_label"],
                "niche_description": n["niche_description"],
                "format": n["format"],
                "rate_low": n["rate_low"],
                "rate_high": n["rate_high"],
                "source": n["source"],
                "assumptions": n["assumptions"],
                "created_at": now,
            }
            for n in niches
        ],
    )


def downgrade() -> None:
    op.drop_table("advertising_benchmarks")
