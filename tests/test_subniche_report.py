# tests/test_subniche_report.py
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection

from nicheradar.domain.profile import CreatorProfile
from nicheradar.integrations.contracts import Cost, Operation
from nicheradar.repositories import schema
from nicheradar.services.budget import Limits, reserve, settle
from nicheradar.services.requests import mark_sent, prepare_request
from nicheradar.subniche_discovery.aggregate import HitMetrics, build_profile
from nicheradar.subniche_discovery.persist import save_measurement
from nicheradar.subniche_discovery.report import ranking, spend_rows
from nicheradar.subniche_discovery.store import approve, create_proposed
from tests.subniche_samples import NOW, channel, draft, make_run, video
from tests.test_subniche_aggregate import hit


def measure(
    db: Connection,
    run_id: UUID,
    slug: str,
    words: str,
    hits: list[HitMetrics],
    *,
    now: datetime = NOW,
) -> None:
    hypothesis_id = create_proposed(db, draft(slug=slug, queries=(words,)), NOW)
    approve(db, slug, NOW)
    save_measurement(
        db,
        hypothesis_id=hypothesis_id,
        run_id=run_id,
        now=now,
        channels=[(channel("a"), [video(1)])],
        hits=hits,
        profile=build_profile(hits, rpm_source="inherited:x"),
    )


@pytest.mark.postgres
def test_ranking_orders_by_traction_then_income_and_lists_examples(db: Connection) -> None:
    run_id, _, _ = make_run(db)
    measure(db, run_id, "weak_one", "weak words", [hit("a", low="10", high="20")])
    measure(
        db,
        run_id,
        "strong_one",
        "strong words",
        [hit("a", traction=True, low="100", high="900"), hit("b", low="50", high="60")],
    )
    measure(
        db, run_id, "medium_one", "medium words", [hit("a", traction=True, low="10", high="30")]
    )
    rows = ranking(db)
    assert [row["slug"] for row in rows] == ["strong_one", "medium_one", "weak_one"]
    assert rows[0]["examples"][0]["income_high"] == "900.00"
    assert rows[0]["rpm_source"] == "inherited:x"
    assert len(rows[0]["examples"]) == 2


@pytest.mark.postgres
def test_ranking_income_decides_ties_and_missing_income_goes_last(db: Connection) -> None:
    run_id, _, _ = make_run(db)
    measure(db, run_id, "no_income", "words w1", [hit("a", traction=True, low=None, high=None)])
    measure(db, run_id, "low_income", "words w2", [hit("a", traction=True, low="10", high="50")])
    measure(db, run_id, "high_income", "words w3", [hit("a", traction=True, low="10", high="500")])
    measure(
        db,
        run_id,
        "more_traction",
        "words w4",
        [hit("a", traction=True, low="1", high="2"), hit("b", traction=True, low="1", high="2")],
    )
    rows = ranking(db)
    assert [row["slug"] for row in rows] == [
        "more_traction",
        "high_income",
        "low_income",
        "no_income",
    ]
    assert rows[-1]["median_income_high"] is None


@pytest.mark.postgres
def test_ranking_reports_only_the_latest_measurement(db: Connection) -> None:
    first_run, analysis_id, _ = make_run(db)
    second_run = uuid4()
    db.execute(
        sa.insert(schema.discovery_runs).values(
            id=second_run,
            analysis_run_id=analysis_id,
            status="running",
            started_at=NOW + timedelta(days=3),
            stats={},
        )
    )
    hypothesis_id = create_proposed(db, draft(slug="repeat", queries=("repeat",)), NOW)
    approve(db, "repeat", NOW)
    for run_id, when, high in (
        (first_run, NOW, "20"),
        (second_run, NOW + timedelta(days=3), "700"),
    ):
        hits = [hit("a", traction=True, low="1", high=high)]
        save_measurement(
            db,
            hypothesis_id=hypothesis_id,
            run_id=run_id,
            now=when,
            channels=[(channel("a"), [video(1)])],
            hits=hits,
            profile=build_profile(hits, rpm_source="inherited:x"),
        )
    rows = ranking(db)
    assert len(rows) == 1
    assert rows[0]["median_income_high"] == "700.00"
    assert rows[0]["measured_at"] == NOW + timedelta(days=3)
    assert [example["income_high"] for example in rows[0]["examples"]] == ["700.00"]


@pytest.mark.postgres
def test_ranking_skips_hypotheses_that_were_never_measured(db: Connection) -> None:
    create_proposed(db, draft(), NOW)
    assert ranking(db) == []


@pytest.mark.postgres
def test_spend_rows_group_by_provider_operation_and_unit(db: Connection) -> None:
    funded = CreatorProfile(
        paid_limits_confirmed=True,
        radar_usd_per_operation=Decimal("0.05"),
        radar_usd_per_run=Decimal("0.10"),
        radar_usd_per_week=Decimal("0.20"),
        radar_usd_per_month=Decimal("1"),
    )
    _, analysis_id, profile_id = make_run(db, profile=funded)
    request_id = prepare_request(
        db, analysis_id, "anthropic", Operation.HYPOTHESIS_PROPOSAL, "scope", "k1", "idem-1", NOW
    )
    reserve(
        db,
        request_id,
        profile_id,
        (Cost(unit="USD", maximum=Decimal("0.05"), source="test"),),
        {"USD": Limits(operation=Decimal(1), run=Decimal(1), week=Decimal(1), period=Decimal(1))},
        NOW,
        "America/Lima",
    )
    mark_sent(db, request_id, NOW)
    settle(db, request_id, profile_id, {"USD": Decimal("0.0015")}, NOW)
    rows = spend_rows(db, NOW - timedelta(days=1))
    assert rows == [
        {
            "provider": "anthropic",
            "operation": "hypothesis_proposal",
            "unit": "USD",
            "calls": 1,
            "amount": "0.001500",
        }
    ]
    assert spend_rows(db, NOW + timedelta(days=1)) == []
