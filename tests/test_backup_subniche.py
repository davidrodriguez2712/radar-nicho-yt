# tests/test_backup_subniche.py
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection

from nicheradar.repositories import schema
from scripts.backup_snapshot import (
    PROVIDER_EVIDENCE_TABLES,
    RUN_TABLES,
    inspect_snapshot,
)
from tests.subniche_samples import NOW, make_run
from tests.test_subniche_schema import hypothesis_row

CURATED = ("niche_hypotheses", "discovery_runs", "hypothesis_snapshots")
API_DATA = ("discovery_channel_snapshots", "hypothesis_channel_hits")


def test_discovery_group_classification() -> None:
    from scripts.backup_snapshot import DISCOVERY_TABLES

    assert DISCOVERY_TABLES == {
        "niche_hypotheses",
        "hypothesis_seed_channels",
        "discovery_runs",
        "hypothesis_snapshots",
    }
    assert not DISCOVERY_TABLES & set(PROVIDER_EVIDENCE_TABLES)
    assert not DISCOVERY_TABLES & RUN_TABLES
    assert set(API_DATA) <= set(PROVIDER_EVIDENCE_TABLES)


@pytest.mark.postgres
def test_curated_subniche_rows_are_backed_up_and_api_rows_excluded(db: Connection) -> None:
    run_id, _, _ = make_run(db)
    hypothesis = hypothesis_row()
    db.execute(sa.insert(schema.niche_hypotheses).values(**hypothesis))
    db.execute(
        sa.insert(schema.hypothesis_snapshots).values(
            id=uuid4(),
            hypothesis_id=hypothesis["id"],
            run_id=run_id,
            measured_at=NOW,
            stable_channels=1,
            traction_channels=0,
            median_income_low=Decimal("10"),
            median_income_high=Decimal("20"),
            profile={},
        )
    )
    retain = NOW + timedelta(days=30)
    db.execute(
        sa.insert(schema.discovery_channel_snapshots).values(
            id=uuid4(),
            run_id=run_id,
            channel_id="UC" + "a" * 22,
            fetched_at=NOW,
            retain_until=retain,
        )
    )
    db.execute(
        sa.insert(schema.hypothesis_channel_hits).values(
            id=uuid4(),
            hypothesis_id=hypothesis["id"],
            run_id=run_id,
            channel_id="UC" + "a" * 22,
            source="search",
            monthly_long_views=1,
            small_channel=True,
            traction=False,
            retain_until=retain,
        )
    )
    report = inspect_snapshot(db)
    counts = report["counts"]
    excluded = report["excluded_rows"]
    assert isinstance(counts, dict) and isinstance(excluded, dict)
    for name in CURATED:
        assert counts[name] == 1
        assert name not in excluded
    for name in API_DATA:
        assert counts[name] == 0
        assert excluded[name] == 1
