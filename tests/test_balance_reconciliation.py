"""Account reconciliation using invented balances only; no network or paid providers."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, func, select, update

from nicheradar.domain.profile import CreatorProfile
from nicheradar.integrations.contracts import (
    Balance,
    Batch,
    Cost,
    Coverage,
    Operation,
    Provenance,
    ProviderError,
)
from nicheradar.integrations.retention import expire, shorten_policy_retention
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record
from nicheradar.repositories.schema import balance_reconciliations, credit_balances
from nicheradar.services.budget import (
    Limits,
    balance_needs_refresh,
    reconcile_balance,
    reserve,
    settle,
)
from nicheradar.services.console import consumption
from nicheradar.services.gateway import Gateway
from nicheradar.services.recovery import prepare_restore
from nicheradar.services.requests import mark_sent, prepare_request
from tests.test_execution import CAPS, COST, request_with_balance
from tests.test_persistence import NOW, seed_evidence

pytestmark = pytest.mark.postgres


class CreditFixture:
    name = "balance-fixture"
    operations = frozenset({Operation.CHANNEL_SEARCH, Operation.BALANCE})

    def __init__(self) -> None:
        self.calls: list[Operation] = []
        self.renewable = Decimal(135)
        self.additional = Decimal(20)
        self.start: datetime | None = NOW - timedelta(days=10)
        self.end = NOW + timedelta(days=20)
        self.unknown_charge = False
        self.observed: datetime | None = None

    async def fetch(self, operation: Operation, parameters: dict[str, Any], now: datetime) -> Batch:
        self.calls.append(operation)
        balance = None
        if operation == Operation.BALANCE:
            balance = Balance(
                renewable=self.renewable,
                additional=self.additional,
                recurring_allocation=Decimal(150),
                cycle_started_at=self.start,
                renews_at=self.end,
            )
        else:
            self.renewable -= 5
            if self.unknown_charge:
                raise ProviderError("timeout", may_have_charged=True)
        return Batch(
            provenance=Provenance(
                provider=self.name,
                operation=operation,
                auth_scope="test",
                fetched_at=now,
                observed_at=self.observed,
                synthetic=True,
            ),
            coverage=Coverage(returned=1 if balance else 0, selection_method="invented fixture"),
            costs=(
                Cost(
                    unit="vidiq_credit",
                    maximum=Decimal(0 if balance else 5),
                    actual=Decimal(0 if balance else 5),
                    source="invented fixture",
                ),
            ),
            balance=balance,
        )


def fixture_gateway(engine: Engine, *, maximum_calls: int = 20, scheduled: bool = False) -> Gateway:
    profile = CreatorProfile(
        paid_limits_confirmed=True, credits_per_run=50, credits_per_week=100, credits_per_cycle=100
    )
    with engine.begin() as db:
        ids = seed_evidence(db)
        db.execute(
            update(s.creator_profiles)
            .where(s.creator_profiles.c.id == ids["profile"])
            .values(configuration=profile.model_dump(mode="json"))
        )
        for usage in ("query", "storage", "history", "scheduled"):
            insert_record(
                db,
                "provider_policies",
                {
                    "provider": CreditFixture.name,
                    "operation": "*",
                    "data_type": "metadata",
                    "usage": usage,
                    "version": "fixture-only",
                    "status": "enabled",
                    "evidence_source": "invented fixture; no account permissions",
                    "effective_at": NOW,
                    "retention_seconds": 3 * 86400,
                },
            )
    return Gateway(
        engine,
        CreditFixture(),
        ids["profile"],
        ids["run"],
        "test",
        profile,
        {
            "vidiq_credit": Limits(
                operation=Decimal(5), run=Decimal(50), week=Decimal(100), period=Decimal(100)
            )
        },
        {
            Operation.CHANNEL_SEARCH: (COST,),
            Operation.BALANCE: (
                Cost(unit="vidiq_credit", maximum=Decimal(0), source="invented free utility"),
            ),
        },
        maximum_calls=maximum_calls,
        scheduled=scheduled,
    )


def latest_reconciliation(db: Connection) -> dict[str, Any]:
    return dict(
        db.execute(
            select(balance_reconciliations)
            .order_by(balance_reconciliations.c.observed_at.desc())
            .limit(1)
        )
        .mappings()
        .one()
    )


def test_consumption_preserves_original_date_and_separates_external_difference(
    db: Connection,
) -> None:
    ids, request = request_with_balance(db)
    reserve(db, request, ids["profile"], (COST,), CAPS, NOW)
    mark_sent(db, request, NOW)
    settle(db, request, ids["profile"], {"vidiq_credit": Decimal(5)}, NOW + timedelta(seconds=1))
    original = db.execute(select(credit_balances)).mappings().one()
    assert original["observed_at"] == NOW
    assert original["refresh_required"] is True
    assert original["renewable_remaining"] == 135  # No invented bucket depletion order.
    reconcile_balance(
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
        NOW + timedelta(minutes=1),
        NOW - timedelta(days=10),
    )
    report = latest_reconciliation(db)
    assert report["balance_change"] == -45
    assert report["radar_consumption"] == 5
    assert report["unattributed_change"] == -40
    assert db.execute(select(credit_balances.c.refresh_required)).scalar_one() is False
    assert db.execute(select(func.count()).select_from(s.cost_ledger)).scalar_one() == 1


def test_external_spend_blocks_already_prepared_request_before_dispatch(db: Connection) -> None:
    ids, request = request_with_balance(db)
    reserve(db, request, ids["profile"], (COST,), CAPS, NOW)
    now = NOW + timedelta(minutes=1)
    reconcile_balance(
        db,
        ids["profile"],
        "vidiq",
        "test",
        Balance(
            renewable=Decimal(3),
            additional=Decimal(0),
            recurring_allocation=Decimal(150),
            renews_at=NOW + timedelta(days=20),
        ),
        now,
        NOW - timedelta(days=10),
    )
    with pytest.raises(ProviderError, match="balance_exhausted"):
        mark_sent(db, request, now)
    assert (
        db.execute(
            select(s.provider_requests.c.sent_at).where(s.provider_requests.c.id == request)
        ).scalar_one()
        is None
    )
    assert db.execute(select(s.cost_reservations.c.status)).scalar_one() == "reserved"


def test_renewal_requires_observation_and_never_rolls_bonus_into_allocation(db: Connection) -> None:
    ids = seed_evidence(db)
    boundary = NOW + timedelta(hours=1)
    reconcile_balance(
        db,
        ids["profile"],
        "vidiq",
        "test",
        Balance(
            renewable=Decimal(0),
            additional=Decimal(20),
            recurring_allocation=Decimal(150),
            renews_at=boundary,
        ),
        NOW,
        NOW - timedelta(days=30),
    )
    before = db.execute(select(credit_balances)).mappings().one()
    assert balance_needs_refresh(dict(before), boundary)
    assert before["renewable_remaining"] == 0
    reconcile_balance(
        db,
        ids["profile"],
        "vidiq",
        "test",
        Balance(
            renewable=Decimal(150),
            additional=Decimal(7),
            recurring_allocation=Decimal(150),
            renews_at=boundary + timedelta(days=30),
        ),
        boundary,
        boundary,
    )
    after = db.execute(select(credit_balances)).mappings().one()
    assert (
        after["renewable_remaining"],
        after["additional_remaining"],
        after["renewable_allocation"],
    ) == (150, 7, 150)
    report = latest_reconciliation(db)
    assert report["kind"] == "cycle_changed"
    assert report["balance_change"] == 137
    assert report["unattributed_change"] is None
    assert not db.execute(select(s.cost_ledger)).all()


@pytest.mark.parametrize(
    "case", ["older", "future_start", "naive", "expired_cycle", "unlimited", "old_cycle_anchor"]
)
def test_invalid_or_stale_observation_cannot_replace_balance(db: Connection, case: str) -> None:
    ids, _ = request_with_balance(db)
    observed, start, end = NOW, NOW - timedelta(days=10), NOW + timedelta(days=20)
    if case == "older":
        observed -= timedelta(seconds=1)
    elif case == "future_start":
        start = NOW + timedelta(seconds=1)
    elif case == "naive":
        observed = NOW.replace(tzinfo=None)
    elif case == "expired_cycle":
        end = NOW
    elif case == "old_cycle_anchor":
        end += timedelta(days=30)
    with pytest.raises(ProviderError):
        reconcile_balance(
            db,
            ids["profile"],
            "vidiq",
            "test",
            Balance(
                renewable=Decimal(1),
                additional=Decimal(0),
                recurring_allocation=Decimal(150),
                renews_at=end,
                unlimited=case == "unlimited",
            ),
            observed,
            start,
        )
    assert db.execute(select(credit_balances.c.renewable_remaining)).scalar_one() == 135


@pytest.mark.parametrize("scheduled", [False, True])
def test_gateway_refreshes_and_reuses_research_without_balance_calls(
    isolated_engine: Engine, scheduled: bool
) -> None:
    gateway = fixture_gateway(isolated_engine, scheduled=scheduled)
    provider = gateway.provider
    assert isinstance(provider, CreditFixture)
    asyncio.run(gateway.fetch(Operation.CHANNEL_SEARCH, {"query": "first"}, NOW))
    assert provider.calls == [Operation.BALANCE, Operation.CHANNEL_SEARCH]
    _, _, cached = asyncio.run(
        gateway.fetch(Operation.CHANNEL_SEARCH, {"query": "first"}, NOW + timedelta(minutes=1))
    )
    assert cached and len(provider.calls) == 2
    provider.renewable -= 10  # Usage outside the radar, invented for this test.
    asyncio.run(
        gateway.fetch(Operation.CHANNEL_SEARCH, {"query": "second"}, NOW + timedelta(minutes=2))
    )
    assert provider.calls == [Operation.BALANCE, Operation.CHANNEL_SEARCH] * 2
    with isolated_engine.connect() as db:
        report = latest_reconciliation(db)
        assert report["radar_consumption"] == 5
        assert report["unattributed_change"] == -10
        assert db.execute(select(func.sum(s.cost_ledger.c.amount))).scalar_one() == 10


def test_free_balance_refresh_counts_toward_durable_batch_limit(isolated_engine: Engine) -> None:
    gateway = fixture_gateway(isolated_engine, maximum_calls=1)
    with pytest.raises(ProviderError, match="batch_limit"):
        asyncio.run(gateway.fetch(Operation.CHANNEL_SEARCH, {"query": "first"}, NOW))
    assert isinstance(gateway.provider, CreditFixture)
    assert gateway.provider.calls == [Operation.BALANCE]
    with pytest.raises(ProviderError, match="batch_limit"):
        asyncio.run(gateway.fetch(Operation.CHANNEL_SEARCH, {"query": "first"}, NOW))
    assert gateway.provider.calls == [Operation.BALANCE]


def test_unknown_charge_survives_balance_refresh_without_paid_repeat(
    isolated_engine: Engine,
) -> None:
    gateway = fixture_gateway(isolated_engine)
    assert isinstance(gateway.provider, CreditFixture)
    gateway.provider.unknown_charge = True
    with pytest.raises(ProviderError, match="timeout"):
        asyncio.run(gateway.fetch(Operation.CHANNEL_SEARCH, {"query": "first"}, NOW))
    asyncio.run(gateway.fetch(Operation.BALANCE, {}, NOW + timedelta(minutes=1)))
    with pytest.raises(ProviderError, match="unknown_charge"):
        asyncio.run(
            gateway.fetch(Operation.CHANNEL_SEARCH, {"query": "first"}, NOW + timedelta(minutes=2))
        )
    assert gateway.provider.calls.count(Operation.CHANNEL_SEARCH) == 1
    with isolated_engine.connect() as db:
        assert (
            db.execute(
                select(s.cost_reservations.c.amount).where(
                    s.cost_reservations.c.status == "unknown_charge"
                )
            ).scalar_one()
            == 5
        )
        assert latest_reconciliation(db)["unattributed_change"] == -5


@pytest.mark.parametrize(
    "case", ["no_cycle", "no_free_tariff", "pending_policy", "unknown_tariff", "future_observation"]
)
def test_refresh_does_not_bypass_configuration(isolated_engine: Engine, case: str) -> None:
    gateway = fixture_gateway(isolated_engine)
    assert isinstance(gateway.provider, CreditFixture)
    error = "balance_refresh_required"
    if case == "no_cycle":
        gateway.provider.start = None
        error = "balance_cycle_required"
    elif case == "no_free_tariff":
        gateway.tariffs[Operation.BALANCE] = (COST,)
    elif case == "pending_policy":
        with isolated_engine.begin() as db:
            db.execute(
                update(s.provider_policies)
                .where(s.provider_policies.c.provider == CreditFixture.name)
                .values(status="pending")
            )
        error = "policy_pending"
    elif case == "unknown_tariff":
        gateway.tariffs[Operation.CHANNEL_SEARCH] = (Cost(unit="vidiq_credit", source="unknown"),)
        error = "unknown_cost"
    else:
        gateway.provider.observed = NOW + timedelta(minutes=1)
        error = "stale_balance_observation"
    with pytest.raises(ProviderError, match=error):
        asyncio.run(gateway.fetch(Operation.CHANNEL_SEARCH, {}, NOW))
    assert Operation.CHANNEL_SEARCH not in gateway.provider.calls
    if case not in {"no_cycle", "future_observation"}:
        assert gateway.provider.calls == []


def test_fixed_subscription_is_not_charged_again_when_spending_credits(
    isolated_engine: Engine,
) -> None:
    gateway = fixture_gateway(isolated_engine)
    with isolated_engine.begin() as db:
        insert_record(
            db,
            "cost_ledger",
            {
                "profile_id": gateway.profile_id,
                "unit": "USD",
                "amount": Decimal(20),
                "kind": "fixed_subscription",
                "external_reference": "fixture-month",
                "occurred_at": NOW,
            },
        )
    asyncio.run(gateway.fetch(Operation.CHANNEL_SEARCH, {}, NOW))
    with isolated_engine.connect() as db:
        result = consumption(db, NOW + timedelta(seconds=1))
        assert {row["unit"]: row["amount"] for row in result["confirmed"]} == {
            "USD": 20,
            "vidiq_credit": 5,
        }
        assert result["balances"][0]["renewable_allocation"] == 150
        assert result["production_estimates_excluded"]


def test_balance_and_derived_differences_obey_source_revocation(isolated_engine: Engine) -> None:
    gateway = fixture_gateway(isolated_engine)
    asyncio.run(gateway.fetch(Operation.BALANCE, {}, NOW))
    asyncio.run(gateway.fetch(Operation.BALANCE, {}, NOW + timedelta(minutes=1)))
    with isolated_engine.begin() as db:
        assert (
            db.execute(select(func.count()).select_from(balance_reconciliations)).scalar_one() == 2
        )
        policy = db.execute(
            select(s.provider_policies.c.id).where(
                s.provider_policies.c.provider == CreditFixture.name,
                s.provider_policies.c.usage == "storage",
            )
        ).scalar_one()
        shorten_policy_retention(db, policy, 0, NOW + timedelta(minutes=2))
        assert not db.execute(select(credit_balances)).all()
        assert not db.execute(select(balance_reconciliations)).all()


def test_manual_balance_expiry_and_restore_preserve_observation_date(db: Connection) -> None:
    request_with_balance(db)
    prepare_restore(db, NOW + timedelta(days=1))
    row = db.execute(select(credit_balances)).mappings().one()
    assert row["observed_at"] == NOW
    assert row["refresh_required"]
    expire(db, NOW + timedelta(days=8))
    assert not db.execute(select(credit_balances)).all()
    assert not db.execute(select(balance_reconciliations)).all()


def test_out_of_order_concurrent_balances_do_not_restore_old_capacity(
    isolated_engine: Engine,
) -> None:
    with isolated_engine.begin() as db:
        ids, _ = request_with_balance(db)

    def observe(index: int) -> str:
        try:
            with isolated_engine.begin() as db:
                reconcile_balance(
                    db,
                    ids["profile"],
                    "vidiq",
                    "test",
                    Balance(
                        renewable=Decimal(135 - index),
                        additional=Decimal(20),
                        recurring_allocation=Decimal(150),
                        renews_at=NOW + timedelta(days=20),
                    ),
                    NOW + timedelta(minutes=index),
                    NOW - timedelta(days=10),
                )
            return "accepted"
        except ProviderError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(observe, [2, 1]))
    assert set(outcomes) <= {"accepted", "stale_balance_observation"}
    with isolated_engine.connect() as db:
        row = db.execute(select(credit_balances)).mappings().one()
        assert row["observed_at"] == NOW + timedelta(minutes=2)
        assert row["renewable_remaining"] == 133


def test_new_run_reconciles_even_a_fresh_balance(isolated_engine: Engine) -> None:
    gateway = fixture_gateway(isolated_engine)
    asyncio.run(gateway.fetch(Operation.BALANCE, {}, NOW))
    with isolated_engine.begin() as db:
        new_run = insert_record(
            db,
            "analysis_runs",
            {
                "profile_id": gateway.profile_id,
                "mode": "synthetic",
                "trigger": "manual",
                "status": "running",
                "configuration": {},
            },
        )
    gateway.run_id = new_run
    asyncio.run(gateway.fetch(Operation.CHANNEL_SEARCH, {}, NOW + timedelta(seconds=1)))
    assert isinstance(gateway.provider, CreditFixture)
    assert gateway.provider.calls == [
        Operation.BALANCE,
        Operation.BALANCE,
        Operation.CHANNEL_SEARCH,
    ]


def test_spend_overlapping_balance_query_requires_another_observation(db: Connection) -> None:
    ids, request = request_with_balance(db)
    reserve(db, request, ids["profile"], (COST,), CAPS, NOW)
    mark_sent(db, request, NOW)
    settle(db, request, ids["profile"], {"vidiq_credit": Decimal(5)}, NOW + timedelta(seconds=1))
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
        NOW + timedelta(seconds=2),
        NOW - timedelta(days=10),
        expected_usage=Decimal(0),
    )
    assert db.execute(select(credit_balances.c.refresh_required)).scalar_one()
    report = latest_reconciliation(db)
    assert report["kind"] == "concurrent_usage"
    assert report["unattributed_change"] is None


def test_observed_renewal_resets_cycle_cap_but_keeps_old_unknown_liability(db: Connection) -> None:
    ids = seed_evidence(db)
    boundary = NOW + timedelta(days=1)
    first = Balance(
        renewable=Decimal(150),
        additional=Decimal(20),
        recurring_allocation=Decimal(150),
        renews_at=boundary,
    )
    reconcile_balance(db, ids["profile"], "vidiq", "test", first, NOW, NOW - timedelta(days=10))
    request = prepare_request(
        db, ids["run"], "vidiq", Operation.CHANNEL_SEARCH, "test", "first", "first", NOW
    )
    caps = {
        "vidiq_credit": Limits(
            operation=Decimal(5), run=Decimal(5), week=Decimal(25), period=Decimal(5)
        )
    }
    reserve(db, request, ids["profile"], (COST,), caps, NOW)
    mark_sent(db, request, NOW)
    settle(db, request, ids["profile"], None, NOW)
    reconcile_balance(
        db,
        ids["profile"],
        "vidiq",
        "test",
        first.model_copy(update={"renews_at": boundary + timedelta(days=30)}),
        boundary,
        boundary,
    )
    new_run = insert_record(
        db,
        "analysis_runs",
        {
            "profile_id": ids["profile"],
            "mode": "synthetic",
            "trigger": "manual",
            "status": "running",
            "configuration": {},
        },
    )
    second = prepare_request(
        db, new_run, "vidiq", Operation.CHANNEL_SEARCH, "test", "second", "second", boundary
    )
    with pytest.raises(ProviderError, match="period_budget_exhausted"):
        reserve(db, second, ids["profile"], (COST,), caps, boundary)
    # Only explicit per-request confirmation resolves an uncertain debit, never renewal itself.
    settle(db, request, ids["profile"], {"vidiq_credit": Decimal(5)}, boundary)
    reconcile_balance(
        db,
        ids["profile"],
        "vidiq",
        "test",
        first.model_copy(update={"renews_at": boundary + timedelta(days=30)}),
        boundary + timedelta(seconds=1),
        boundary,
    )
    reserve(db, second, ids["profile"], (COST,), caps, boundary + timedelta(seconds=1))


def test_same_timestamp_remote_observation_cannot_overwrite_snapshot(
    isolated_engine: Engine,
) -> None:
    gateway = fixture_gateway(isolated_engine)
    asyncio.run(gateway.fetch(Operation.BALANCE, {}, NOW))
    assert isinstance(gateway.provider, CreditFixture)
    gateway.provider.renewable = Decimal(150)
    with pytest.raises(ProviderError, match="stale_balance_observation"):
        asyncio.run(gateway.fetch(Operation.BALANCE, {}, NOW))
    with isolated_engine.connect() as db:
        assert db.execute(select(credit_balances.c.renewable_remaining)).scalar_one() == 135


def test_shortened_retention_removes_derived_difference_without_losing_new_snapshot(
    isolated_engine: Engine,
) -> None:
    gateway = fixture_gateway(isolated_engine)
    _, first, _ = asyncio.run(gateway.fetch(Operation.BALANCE, {}, NOW))
    _, second, _ = asyncio.run(gateway.fetch(Operation.BALANCE, {}, NOW + timedelta(hours=1)))
    with isolated_engine.begin() as db:
        policy = db.execute(
            select(s.raw_observations.c.policy_id).where(s.raw_observations.c.id == first)
        ).scalar_one()
        shorten_policy_retention(db, policy, 7200, NOW + timedelta(hours=2))
        assert db.execute(select(credit_balances.c.source_observation_id)).scalar_one() == second
        assert db.execute(select(credit_balances.c.retain_until)).scalar_one() == NOW + timedelta(
            hours=3
        )
        assert not db.execute(select(balance_reconciliations)).all()
        assert consumption(db, NOW + timedelta(hours=3))["balances"] == []


def test_manual_cycle_anchor_is_explicit_and_does_not_guess_next_cycle(
    isolated_engine: Engine,
) -> None:
    gateway = fixture_gateway(isolated_engine)
    assert isinstance(gateway.provider, CreditFixture)
    gateway.provider.start = None
    gateway.provider.end = NOW + timedelta(hours=1)
    gateway.credit_cycle_started_at = NOW - timedelta(days=10)
    asyncio.run(gateway.fetch(Operation.BALANCE, {}, NOW))
    gateway.provider.end = NOW + timedelta(days=30)
    with pytest.raises(ProviderError, match="balance_cycle_required"):
        asyncio.run(gateway.fetch(Operation.BALANCE, {}, NOW + timedelta(hours=2)))
    gateway.credit_cycle_started_at = NOW + timedelta(hours=1)
    asyncio.run(gateway.fetch(Operation.BALANCE, {}, NOW + timedelta(hours=3)))
    with isolated_engine.connect() as db:
        assert latest_reconciliation(db)["kind"] == "cycle_changed"


def test_prepared_request_can_resume_without_counting_its_slot_twice(
    isolated_engine: Engine,
) -> None:
    from nicheradar.integrations.cache import cache_key

    gateway = fixture_gateway(isolated_engine, maximum_calls=1)
    key = cache_key(gateway.provider.name, Operation.BALANCE, {}, gateway.auth_scope)
    with isolated_engine.begin() as db:
        request = prepare_request(
            db,
            gateway.run_id,
            gateway.provider.name,
            Operation.BALANCE,
            gateway.auth_scope,
            key,
            f"{gateway.run_id}:{key}",
            NOW,
        )
        reserve(
            db, request, gateway.profile_id, gateway.tariffs[Operation.BALANCE], gateway.limits, NOW
        )
    asyncio.run(gateway.fetch(Operation.BALANCE, {}, NOW))
    assert isinstance(gateway.provider, CreditFixture)
    assert gateway.provider.calls == [Operation.BALANCE]
