"""La liberación solo toca evidence con cobro desconocido y desbloquea la ficha."""

import json
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine

from nicheradar.repositories import schema_v1 as s
from scripts.release_unknown_evidence_requests import release_unknown_evidence_requests
from tests.test_market_intel_classify import seed_run
from tests.test_market_intel_evidence import base
from tests.test_market_intel_evidence_stage import (
    NOW,
    FakeSource,
    context,
    make_run,
    rows,
    run_stage,
    seed,
    selector_answering,
)

URL = "https://media.dealbaron.com/listing-attachments/a.png"


def requests_by_state(engine: Engine) -> dict[str, int]:
    with engine.connect() as connection:
        found = connection.execute(
            sa.select(s.provider_requests.c.state, sa.func.count()).group_by(
                s.provider_requests.c.state
            )
        )
        return {str(row[0]): int(row[1]) for row in found.all()}


def fail_one(engine: Engine) -> dict[str, Any]:
    """One listing whose model call fails: its request is left with an unknown charge."""
    run = make_run(engine)
    with engine.begin() as connection:
        seed(connection, "one")
    ctx = context(engine, run, FakeSource({"one": (URL,)}))
    run_stage(ctx, selector_answering(None))
    assert requests_by_state(engine) == {"unknown_charge": 1}
    return run


def insert_request(
    engine: Engine, run: dict[str, Any], *, provider: str, operation: str, state: str, sent_ago: int
) -> None:
    with engine.begin() as connection:
        request_id = connection.execute(
            s.provider_requests.insert()
            .values(
                run_id=run["id"],
                provider=provider,
                operation=operation,
                auth_scope="x",
                cache_key=uuid4().hex,
                idempotency_key=uuid4().hex,
                state=state,
                sent_at=NOW - timedelta(minutes=sent_ago),
                created_at=NOW,
            )
            .returning(s.provider_requests.c.id)
        ).scalar_one()
        connection.execute(
            s.cost_reservations.insert().values(
                request_id=request_id,
                profile_id=run["profile_id"],
                unit="USD",
                amount=Decimal("0.105"),
                status="unknown_charge" if state == "unknown_charge" else "reserved",
                period_start=NOW - timedelta(days=1),
                period_end=NOW + timedelta(days=1),
                created_at=NOW,
            )
        )


@pytest.mark.postgres
def test_a_dry_run_reports_and_writes_nothing(isolated_engine: Engine) -> None:
    fail_one(isolated_engine)
    result = release_unknown_evidence_requests(isolated_engine, apply=False, now=NOW)
    assert result["requests"] == 1 and result["unknown_charge"] == 1
    assert Decimal(str(result["reservation_usd_freed"])) > 0
    assert requests_by_state(isolated_engine) == {"unknown_charge": 1}


@pytest.mark.postgres
def test_applying_settles_the_request_as_zero_and_frees_the_reservation(
    isolated_engine: Engine,
) -> None:
    fail_one(isolated_engine)
    release_unknown_evidence_requests(isolated_engine, apply=True, now=NOW)
    assert requests_by_state(isolated_engine) == {"completed": 1}
    with isolated_engine.connect() as connection:
        reservation = connection.execute(sa.select(s.cost_reservations)).mappings().one()
        ledger = connection.execute(sa.select(s.cost_ledger)).mappings().all()
    assert reservation["status"] == "confirmed" and reservation["amount"] == 0
    assert len(ledger) == 1 and ledger[0]["amount"] == 0 and ledger[0]["kind"] == "provider_usage"


@pytest.mark.postgres
def test_it_is_idempotent(isolated_engine: Engine) -> None:
    fail_one(isolated_engine)
    release_unknown_evidence_requests(isolated_engine, apply=True, now=NOW)
    again = release_unknown_evidence_requests(isolated_engine, apply=True, now=NOW)
    assert again["requests"] == 0


def another_run(engine: Engine, run: dict[str, Any]) -> dict[str, Any]:
    """A later manual run, as in production: its own analysis run, so its own idempotency keys."""
    with engine.begin() as connection:
        return seed_run(connection, run["profile_id"])


@pytest.mark.postgres
def test_a_blocked_listing_is_processed_again_after_the_release(isolated_engine: Engine) -> None:
    first = fail_one(isolated_engine)
    good = selector_answering(json.dumps(base()))
    ctx = context(isolated_engine, another_run(isolated_engine, first), FakeSource({"one": (URL,)}))
    blocked = run_stage(ctx, good)
    assert blocked["skipped"] == 1 and blocked["complete"] == 0 and rows(isolated_engine) == []
    release_unknown_evidence_requests(isolated_engine, apply=True, now=NOW)
    ctx = context(isolated_engine, another_run(isolated_engine, first), FakeSource({"one": (URL,)}))
    freed = run_stage(ctx, good)
    assert freed["complete"] == 1 and rows(isolated_engine)[0]["extraction_state"] == "complete"


@pytest.mark.postgres
def test_it_never_touches_other_operations_or_providers(isolated_engine: Engine) -> None:
    run = make_run(isolated_engine)
    insert_request(
        isolated_engine,
        run,
        provider="youtube",
        operation="listing_evidence",
        state="unknown_charge",
        sent_ago=0,
    )
    insert_request(
        isolated_engine,
        run,
        provider="openai",
        operation="market_listing_classify",
        state="unknown_charge",
        sent_ago=0,
    )
    result = release_unknown_evidence_requests(isolated_engine, apply=True, now=NOW)
    assert result["requests"] == 0
    assert requests_by_state(isolated_engine) == {"unknown_charge": 2}


@pytest.mark.postgres
def test_a_recent_sent_request_is_left_alone_and_a_stale_one_is_released(
    isolated_engine: Engine,
) -> None:
    run = make_run(isolated_engine)
    insert_request(
        isolated_engine,
        run,
        provider="openai",
        operation="listing_evidence",
        state="sent",
        sent_ago=5,
    )
    insert_request(
        isolated_engine,
        run,
        provider="openai",
        operation="listing_evidence",
        state="sent",
        sent_ago=120,
    )
    result = release_unknown_evidence_requests(isolated_engine, apply=True, now=NOW)
    assert result["requests"] == 1 and result["sent_stale"] == 1
    assert requests_by_state(isolated_engine) == {"sent": 1, "completed": 1}
