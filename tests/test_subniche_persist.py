# tests/test_subniche_persist.py
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection

from nicheradar.repositories import schema
from nicheradar.repositories.core import insert_record
from nicheradar.subniche_discovery.aggregate import build_profile
from nicheradar.subniche_discovery.persist import API_RETENTION, rpm_range, save_measurement
from nicheradar.subniche_discovery.store import create_proposed, get_hypothesis
from tests.subniche_samples import NOW, channel, draft, make_run, video
from tests.test_subniche_aggregate import hit


@pytest.mark.postgres
def test_save_measurement_writes_snapshots_hits_and_the_profile(db: Connection) -> None:
    run_id, _, _ = make_run(db)
    hypothesis_id = create_proposed(db, draft(), NOW)
    chan = channel("a")
    hits = [hit("a")]
    profile = build_profile(hits, rpm_source=None)
    save_measurement(
        db,
        hypothesis_id=hypothesis_id,
        run_id=run_id,
        now=NOW,
        channels=[(chan, [video(1), video(2)])],
        hits=hits,
        profile=profile,
    )
    snapshot = db.execute(sa.select(schema.discovery_channel_snapshots)).mappings().one()
    assert snapshot["retain_until"] == NOW + API_RETENTION
    assert [v["views"] for v in snapshot["recent_videos"]] == [30_000, 30_000]
    stored = db.execute(sa.select(schema.hypothesis_channel_hits)).mappings().one()
    assert stored["retain_until"] == NOW + API_RETENTION and stored["flags"] == []
    summary = db.execute(sa.select(schema.hypothesis_snapshots)).mappings().one()
    assert summary["stable_channels"] == 1 and summary["median_income_low"] == Decimal("100.00")
    assert get_hypothesis(db, "history_revenge")["last_measured_at"] == NOW


@pytest.mark.postgres
def test_rpm_range_reads_the_long_format_benchmark_or_none(db: Connection) -> None:
    assert rpm_range(db, None) is None
    assert rpm_range(db, "no_such_niche") is None
    label = "test_subniche_long_rpm"
    insert_record(
        db,
        "advertising_benchmarks",
        {
            "niche_label": label,
            "niche_description": "fixture",
            "format": "long",
            "rate_low": Decimal("3.5"),
            "rate_high": Decimal("8"),
            "source": "fixture",
            "assumptions": "fixture",
            "created_at": NOW,
        },
    )
    found = rpm_range(db, label)
    assert found is not None
    low, high, source = found
    assert (low, high) == (Decimal("3.5"), Decimal("8"))
    assert source == f"inherited:{label}"
