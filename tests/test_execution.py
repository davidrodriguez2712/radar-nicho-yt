from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, Engine, func, select, update

from nicheradar.domain.profile import CreatorProfile
from nicheradar.integrations.contracts import Balance, Cost, Operation, ProviderError
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record
from nicheradar.services.budget import Limits, calendar_windows, reconcile_balance, reserve, settle
from nicheradar.services.requests import mark_sent, prepare_request, recover_uncertain_requests
from nicheradar.workers.queue import (
    claim,
    confirm_stage,
    create_schedule,
    enqueue,
    fail_job,
    heartbeat,
    schedule_due,
)
from tests.test_persistence import NOW, seed_evidence

pytestmark = pytest.mark.postgres
COST = Cost(unit="vidiq_credit", maximum=Decimal(5), source="synthetic test cost")
CAPS = {
    "vidiq_credit": Limits(
        operation=Decimal(5), run=Decimal(5), week=Decimal(25), period=Decimal(100)
    )
}


def request_with_balance(db: Connection) -> tuple[dict[str, UUID], UUID]:
    ids = seed_evidence(db)
    reconcile_balance(
        db,
        ids["profile"],
        "vidiq",
        "test",
        Balance(
            renewable=Decimal(135),
            additional=Decimal(20),
            recurring_allocation=Decimal(150),
            renews_at=NOW + timedelta(days=20),
        ),
        NOW,
        NOW - timedelta(days=10),
    )
    request = prepare_request(
        db, ids["run"], "vidiq", Operation.CHANNEL_SEARCH, "test", "key", f"request-{uuid4()}", NOW
    )
    return ids, request


def test_credit_reservation_unknown_charge_and_recovery(db: Connection) -> None:
    ids, request = request_with_balance(db)
    reserve(db, request, ids["profile"], (COST,), CAPS, NOW)
    mark_sent(db, request, NOW)
    assert recover_uncertain_requests(db, ids["run"]) == 1
    with pytest.raises(ProviderError, match="request_requires_reconciliation"):
        mark_sent(db, request, NOW)
    assert db.execute(select(s.cost_reservations.c.status)).scalar_one() == "unknown_charge"
    settle(db, request, ids["profile"], {"vidiq_credit": Decimal(5)}, NOW)
    settle(db, request, ids["profile"], {"vidiq_credit": Decimal(5)}, NOW)
    assert db.execute(select(func.count()).select_from(s.cost_ledger)).scalar_one() == 1
    assert db.execute(select(s.cost_ledger.c.unit)).scalar_one() == "vidiq_credit"
    assert db.execute(select(s.cost_reservations.c.status)).scalar_one() == "confirmed"


def test_unknown_cost_and_run_ceiling(db: Connection) -> None:
    ids, request = request_with_balance(db)
    with pytest.raises(ProviderError, match="unknown_cost"):
        reserve(db, request, ids["profile"], (Cost(unit="USD", source="unknown"),), CAPS, NOW)
    reserve(db, request, ids["profile"], (COST,), CAPS, NOW)
    second = prepare_request(
        db, ids["run"], "vidiq", Operation.OUTLIERS, "test", "key2", "key2", NOW
    )
    with pytest.raises(ProviderError, match="run_budget_exhausted"):
        reserve(db, second, ids["profile"], (COST,), CAPS, NOW)


def test_balance_external_spend_and_renewal_not_bonus(db: Connection) -> None:
    ids, _ = request_with_balance(db)
    change = reconcile_balance(
        db,
        ids["profile"],
        "vidiq",
        "test",
        Balance(
            renewable=Decimal(100),
            additional=Decimal(10),
            recurring_allocation=Decimal(150),
            renews_at=NOW + timedelta(days=20),
        ),
        NOW,
        NOW - timedelta(days=10),
    )
    assert change == -45
    row = db.execute(select(s.credit_balances)).mappings().one()
    assert row["renewable_allocation"] == 150
    assert row["additional_remaining"] == 10
    assert not db.execute(select(s.cost_ledger)).all()


def test_concurrent_reservations_share_cap(isolated_engine: Engine) -> None:
    scope = str(uuid4())
    with isolated_engine.begin() as db:
        profile = insert_record(db, "creator_profiles", {"profile_key": scope, "configuration": {}})
        reconcile_balance(
            db,
            profile,
            "vidiq",
            scope,
            Balance(
                renewable=Decimal(150),
                additional=Decimal(20),
                recurring_allocation=Decimal(150),
                renews_at=NOW + timedelta(days=20),
            ),
            NOW,
            NOW - timedelta(days=10),
        )
        requests = []
        for _ in range(2):
            run = insert_record(
                db,
                "analysis_runs",
                {
                    "profile_id": profile,
                    "mode": "synthetic",
                    "trigger": "manual",
                    "status": "running",
                    "configuration": {},
                },
            )
            requests.append(
                prepare_request(
                    db,
                    run,
                    "vidiq",
                    Operation.CHANNEL_SEARCH,
                    scope,
                    str(uuid4()),
                    str(uuid4()),
                    NOW,
                )
            )
    caps = {
        "vidiq_credit": Limits(
            operation=Decimal(5), run=Decimal(5), week=Decimal(5), period=Decimal(5)
        )
    }

    def attempt(request_id: UUID) -> str:
        try:
            with isolated_engine.begin() as connection:
                reserve(connection, request_id, profile, (COST,), caps, NOW)
            return "reserved"
        except ProviderError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, requests))
    assert sorted(outcomes) == ["period_budget_exhausted", "reserved"]


def test_calendar_lima_utc() -> None:
    week, month, following = calendar_windows(NOW, "America/Lima")
    assert week.hour == month.hour == following.hour == 5
    assert month.day == following.day == 1


def test_free_balance_refresh_needs_no_previous_balance(db: Connection) -> None:
    ids = seed_evidence(db)
    request = prepare_request(
        db, ids["run"], "vidiq", Operation.BALANCE, "fresh", "balance", "balance", NOW
    )
    free = Cost(unit="vidiq_credit", maximum=Decimal(0), source="verified free utility")
    reserve(db, request, ids["profile"], (free,), CAPS, NOW)
    mark_sent(db, request, NOW)
    settle(db, request, ids["profile"], {"vidiq_credit": Decimal(0)}, NOW)
    assert (
        db.execute(
            select(s.provider_requests.c.state).where(s.provider_requests.c.id == request)
        ).scalar_one()
        == "completed"
    )


def test_persisted_profile_caps_override_looser_caller_limits(db: Connection) -> None:
    ids, request = request_with_balance(db)
    profile = CreatorProfile(credits_per_run=4)
    db.execute(
        update(s.creator_profiles)
        .where(s.creator_profiles.c.id == ids["profile"])
        .values(configuration=profile.model_dump(mode="json"))
    )
    with pytest.raises(ProviderError, match="run_budget_exhausted"):
        reserve(db, request, ids["profile"], (COST,), CAPS, NOW)


def test_shared_usd_ceiling_counts_fixed_costs_and_reserve(db: Connection) -> None:
    ids = seed_evidence(db)
    profile = CreatorProfile(
        monthly_reserve_usd=Decimal(10),
        radar_usd_per_operation=Decimal(150),
        radar_usd_per_run=Decimal(150),
        radar_usd_per_week=Decimal(150),
        radar_usd_per_month=Decimal(150),
    )
    db.execute(
        update(s.creator_profiles)
        .where(s.creator_profiles.c.id == ids["profile"])
        .values(configuration=profile.model_dump(mode="json"))
    )
    insert_record(
        db,
        "cost_ledger",
        {
            "profile_id": ids["profile"],
            "unit": "USD",
            "amount": Decimal(138),
            "kind": "fixed_subscription",
            "external_reference": "synthetic-monthly-fixed-cost",
            "occurred_at": NOW,
        },
    )
    request = prepare_request(
        db, ids["run"], "paid-api", Operation.CHANNEL_SEARCH, "test", "usd", "usd", NOW
    )
    caps = {
        "USD": Limits(
            operation=Decimal(999), run=Decimal(999), week=Decimal(999), period=Decimal(999)
        )
    }
    with pytest.raises(ProviderError, match="shared_budget_exhausted"):
        reserve(
            db,
            request,
            ids["profile"],
            (Cost(unit="USD", maximum=Decimal(3), source="test"),),
            caps,
            NOW,
        )
    reserve(
        db,
        request,
        ids["profile"],
        (Cost(unit="USD", maximum=Decimal(2), source="test"),),
        caps,
        NOW,
    )


def test_jobs_resume_confirmed_stage_and_reject_stale_owner(db: Connection) -> None:
    ids = seed_evidence(db)
    job_id = enqueue(db, ids["profile"], "manual-1", NOW, {})
    assert enqueue(db, ids["profile"], "manual-1", NOW, {}) == job_id
    job = claim(db, "worker-a", NOW, lease_seconds=30)
    assert job is not None
    assert job["id"] == job_id
    confirm_stage(db, job_id, "worker-a", NOW, "planning", {"family": "science"})
    heartbeat(db, job_id, "worker-a", NOW, lease_seconds=30)
    assert claim(db, "worker-b", NOW) is None
    recovered = claim(db, "worker-b", NOW + timedelta(seconds=31))
    assert recovered is not None
    assert recovered["stage"] == "query"
    assert recovered["checkpoints"] == {"planning": {"family": "science"}}
    with pytest.raises(ProviderError, match="lease_lost"):
        confirm_stage(db, job_id, "worker-a", NOW + timedelta(seconds=31), "query", {})


def test_scheduler_coalesces_missed_hours_and_pauses(db: Connection) -> None:
    ids = seed_evidence(db)
    create_schedule(db, ids["profile"], NOW - timedelta(days=5), {})
    assert not schedule_due(db, NOW, globally_paused=False)
    db.execute(update(s.radar_schedules).values(paused=False))
    assert not schedule_due(db, NOW)
    assert len(schedule_due(db, NOW, globally_paused=False)) == 1
    assert not schedule_due(db, NOW, globally_paused=False)
    assert db.execute(select(s.radar_schedules.c.next_due_at)).scalar_one() > NOW


def test_safe_retries_bounded_and_quota_deferred(db: Connection) -> None:
    ids = seed_evidence(db)
    job_id = enqueue(db, ids["profile"], "retries", NOW, {})
    now = NOW
    for attempt in range(3):
        job = claim(db, "worker", now)
        assert job is not None
        assert job["attempts"] == attempt + 1
        fail_job(db, job_id, "worker", now, ProviderError("connect", retry_safe=True))
        now += timedelta(hours=1)
    assert claim(db, "worker", now) is None
    quota_job = enqueue(db, ids["profile"], "quota", now, {})
    assert claim(db, "worker", now) is not None
    fail_job(db, quota_job, "worker", now, ProviderError("quota"))
    assert claim(db, "worker", now + timedelta(days=1)) is None
