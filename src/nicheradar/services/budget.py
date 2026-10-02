from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import Field
from sqlalchemy import Connection, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from nicheradar.domain.profile import CreatorProfile
from nicheradar.integrations.contracts import Balance, Contract, Cost, ProviderError
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record
from nicheradar.repositories.schema import balance_reconciliations, credit_balances


class Limits(Contract):
    operation: Decimal = Field(ge=0)
    run: Decimal = Field(ge=0)
    week: Decimal = Field(ge=0)
    period: Decimal = Field(ge=0)


def calendar_windows(now: datetime, timezone: str) -> tuple[datetime, datetime, datetime]:
    local = now.astimezone(ZoneInfo(timezone))
    day = local.replace(hour=0, minute=0, second=0, microsecond=0)
    week = day - timedelta(days=day.weekday())
    month = day.replace(day=1)
    following = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    return week.astimezone(UTC), month.astimezone(UTC), following.astimezone(UTC)


def lock_profile(connection: Connection, profile_id: UUID) -> None:
    connection.execute(
        select(s.creator_profiles.c.id)
        .where(s.creator_profiles.c.id == profile_id)
        .with_for_update()
    ).scalar_one()


def lock_account(connection: Connection, provider: str, auth_scope: str) -> None:
    # Also serializes a first observation, when there is no balance row to lock yet.
    connection.execute(
        select(
            func.pg_advisory_xact_lock(
                func.hashtextextended(f"balance:{len(provider)}:{provider}:{auth_scope}", 0)
            )
        )
    )


def credit_usage(connection: Connection, provider: str, auth_scope: str, unit: str) -> Decimal:
    return Decimal(
        connection.execute(
            select(func.coalesce(func.sum(s.cost_ledger.c.amount), 0))
            .join(s.provider_requests, s.provider_requests.c.id == s.cost_ledger.c.request_id)
            .where(
                s.provider_requests.c.provider == provider,
                s.provider_requests.c.auth_scope == auth_scope,
                s.cost_ledger.c.unit == unit,
            )
        ).scalar_one()
    )


def balance_needs_refresh(balance: Mapping[str, Any] | None, now: datetime) -> bool:
    return (
        balance is None
        or balance["refresh_required"]
        or balance["observed_at"] < now - timedelta(hours=1)
        or balance["observed_at"] > now
        or balance["renews_at"] <= now
        or balance["retain_until"] is None
        or balance["retain_until"] <= now
    )


def validate_reserved_balance(connection: Connection, request_id: UUID, now: datetime) -> None:
    """A newly observed external spend can invalidate an already prepared reservation."""
    request = (
        connection.execute(
            select(s.provider_requests).where(s.provider_requests.c.id == request_id)
        )
        .mappings()
        .one()
    )
    lock_account(connection, request["provider"], request["auth_scope"])
    units = (
        connection.execute(
            select(s.cost_reservations.c.unit).where(
                s.cost_reservations.c.request_id == request_id,
                s.cost_reservations.c.unit.endswith("_credit"),
                s.cost_reservations.c.status == "reserved",
                s.cost_reservations.c.amount > 0,
            )
        )
        .scalars()
        .all()
    )
    for unit in units:
        balance = (
            connection.execute(
                select(credit_balances).where(
                    credit_balances.c.provider == request["provider"],
                    credit_balances.c.auth_scope == request["auth_scope"],
                )
            )
            .mappings()
            .first()
        )
        if balance_needs_refresh(dict(balance) if balance else None, now):
            raise ProviderError("balance_refresh_required")
        assert balance is not None
        if balance["unit"] != unit:
            raise ProviderError("balance_unit_mismatch")
        held = connection.execute(
            select(func.coalesce(func.sum(s.cost_reservations.c.amount), 0))
            .join(s.provider_requests, s.provider_requests.c.id == s.cost_reservations.c.request_id)
            .where(
                s.provider_requests.c.provider == request["provider"],
                s.provider_requests.c.auth_scope == request["auth_scope"],
                s.cost_reservations.c.unit == unit,
                s.cost_reservations.c.status.in_(["reserved", "unknown_charge"]),
            )
        ).scalar_one()
        if held > balance["renewable_remaining"] + balance["additional_remaining"]:
            raise ProviderError("balance_exhausted")


def reserve(
    connection: Connection,
    request_id: UUID,
    profile_id: UUID,
    costs: tuple[Cost, ...],
    limits: dict[str, Limits],
    now: datetime,
    timezone: str = "America/Lima",
) -> list[UUID]:
    """Caller MUST commit before sending. A failed preflight rolls back the transaction."""
    lock_profile(connection, profile_id)
    profile = CreatorProfile.model_validate(
        connection.execute(
            select(s.creator_profiles.c.configuration).where(s.creator_profiles.c.id == profile_id)
        ).scalar_one()
    )
    request = (
        connection.execute(
            select(s.provider_requests)
            .where(s.provider_requests.c.id == request_id)
            .with_for_update()
        )
        .mappings()
        .one()
    )
    existing = list(
        connection.execute(
            select(s.cost_reservations.c.id).where(s.cost_reservations.c.request_id == request_id)
        ).scalars()
    )
    if existing or request["state"] != "prepared":
        raise ProviderError("request_already_reserved")
    trigger = connection.execute(
        select(s.analysis_runs.c.trigger).where(s.analysis_runs.c.id == request["run_id"])
    ).scalar_one()
    lock_account(connection, request["provider"], request["auth_scope"])
    week_start, month_start, month_end = calendar_windows(now, timezone)
    reservations = []
    if len({cost.unit for cost in costs}) != len(costs):
        raise ValueError("duplicate cost unit")
    for cost in sorted(costs, key=lambda entry: entry.unit):
        if cost.maximum is None or cost.unit not in limits:
            raise ProviderError("unknown_cost")
        maximum, cap = cost.maximum, limits[cost.unit]
        period_start, period_end = month_start, month_end
        if cost.unit == "USD":
            cap = Limits(
                operation=min(cap.operation, profile.radar_usd_per_operation),
                run=min(cap.run, profile.radar_usd_per_run),
                week=min(cap.week, profile.radar_usd_per_week),
                period=min(cap.period, profile.radar_usd_per_month),
            )
        elif cost.unit == "vidiq_credit":
            run_cap = (
                profile.channel_analysis_credits_per_run
                if trigger == "channel_analysis"
                else profile.credits_per_run
            )
            cap = Limits(
                operation=cap.operation,
                run=min(cap.run, Decimal(run_cap)),
                week=min(cap.week, Decimal(profile.credits_per_week)),
                period=min(cap.period, Decimal(profile.credits_per_cycle)),
            )
        if cost.unit.endswith("_credit") and maximum > 0:
            balance = (
                connection.execute(
                    select(credit_balances)
                    .where(
                        credit_balances.c.provider == request["provider"],
                        credit_balances.c.auth_scope == request["auth_scope"],
                    )
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if balance_needs_refresh(dict(balance) if balance else None, now):
                raise ProviderError("balance_refresh_required")
            assert balance is not None
            if balance["unit"] != cost.unit:
                raise ProviderError("balance_unit_mismatch")
            period_start, period_end = balance["cycle_started_at"], balance["renews_at"]
            held = connection.execute(
                select(func.coalesce(func.sum(s.cost_reservations.c.amount), 0))
                .join(
                    s.provider_requests,
                    s.provider_requests.c.id == s.cost_reservations.c.request_id,
                )
                .where(
                    s.provider_requests.c.provider == request["provider"],
                    s.provider_requests.c.auth_scope == request["auth_scope"],
                    s.cost_reservations.c.unit == cost.unit,
                    s.cost_reservations.c.status.in_(["reserved", "unknown_charge"]),
                )
            ).scalar_one()
            if maximum + held > balance["renewable_remaining"] + balance["additional_remaining"]:
                raise ProviderError("balance_exhausted")

        def used(start: datetime, *, this_run: bool = False, unit: str = cost.unit) -> Decimal:
            conditions = [
                s.cost_reservations.c.profile_id == profile_id,
                s.cost_reservations.c.unit == unit,
                s.cost_reservations.c.status.in_(["reserved", "unknown_charge", "confirmed"]),
            ]
            # Uncertain/open reservations remain liabilities even across a period boundary.
            conditions.append(
                (s.cost_reservations.c.created_at >= start)
                | s.cost_reservations.c.status.in_(["reserved", "unknown_charge"])
            )
            if this_run:
                conditions.append(s.provider_requests.c.run_id == request["run_id"])
            value = connection.execute(
                select(func.coalesce(func.sum(s.cost_reservations.c.amount), 0))
                .join(
                    s.provider_requests,
                    s.provider_requests.c.id == s.cost_reservations.c.request_id,
                )
                .where(*conditions)
            ).scalar_one()
            if not this_run:
                # Fixed subscriptions/manual costs have no provider request: count USD once.
                value += connection.execute(
                    select(func.coalesce(func.sum(s.cost_ledger.c.amount), 0)).where(
                        s.cost_ledger.c.profile_id == profile_id,
                        s.cost_ledger.c.unit == unit,
                        s.cost_ledger.c.request_id.is_(None),
                        s.cost_ledger.c.occurred_at >= start,
                    )
                ).scalar_one()
            return Decimal(value)

        if cost.unit == "USD" and maximum > 0:
            remaining_envelope = profile.monthly_ceiling_usd - profile.monthly_reserve_usd
            if used(month_start) + maximum > remaining_envelope:
                raise ProviderError("shared_budget_exhausted")
        # A verified zero-cost balance refresh must work even when paid budgets are exhausted.
        if maximum > 0 and (
            maximum > cap.operation or used(period_start, this_run=True) + maximum > cap.run
        ):
            raise ProviderError("run_budget_exhausted")
        if maximum > 0 and (
            used(week_start) + maximum > cap.week or used(period_start) + maximum > cap.period
        ):
            raise ProviderError("period_budget_exhausted")
        reservations.append(
            insert_record(
                connection,
                "cost_reservations",
                {
                    "request_id": request_id,
                    "profile_id": profile_id,
                    "unit": cost.unit,
                    "amount": maximum,
                    "status": "reserved",
                    "period_start": period_start,
                    "period_end": period_end,
                    "created_at": now,
                },
            )
        )
    return reservations


def reconcile_balance(
    connection: Connection,
    profile_id: UUID,
    provider: str,
    auth_scope: str,
    balance: Balance,
    observed_at: datetime,
    cycle_started_at: datetime,
    *,
    unit: str = "vidiq_credit",
    source_observation_id: UUID | None = None,
    retain_until: datetime | None = None,
    expected_usage: Decimal | None = None,
) -> Decimal:
    lock_profile(connection, profile_id)
    lock_account(connection, provider, auth_scope)
    if (
        balance.renewable is None
        or balance.recurring_allocation is None
        or balance.renews_at is None
        or balance.unlimited
    ):
        raise ProviderError("balance_not_finite_or_dated")
    if (
        observed_at.tzinfo is None
        or cycle_started_at.tzinfo is None
        or not cycle_started_at <= observed_at < balance.renews_at
        or not unit.endswith("_credit")
    ):
        raise ProviderError("balance_cycle_required")
    # Direct observations are identified manual inputs; remote snapshots must reference raw data.
    retain_until = retain_until or observed_at + timedelta(days=7)
    if source_observation_id:
        raw = (
            connection.execute(
                select(
                    s.raw_observations.c.retain_until,
                    s.provider_requests.c.provider,
                    s.provider_requests.c.auth_scope,
                    s.provider_requests.c.operation,
                )
                .join(
                    s.provider_requests, s.provider_requests.c.id == s.raw_observations.c.request_id
                )
                .where(s.raw_observations.c.id == source_observation_id)
            )
            .mappings()
            .one()
        )
        if (raw["provider"], raw["auth_scope"], raw["operation"]) != (
            provider,
            auth_scope,
            "balance",
        ):
            raise ProviderError("balance_source_mismatch")
        retain_until = min(retain_until, raw["retain_until"])
    if retain_until <= observed_at:
        raise ProviderError("balance_refresh_required")
    previous = (
        connection.execute(
            select(credit_balances)
            .where(
                credit_balances.c.provider == provider,
                credit_balances.c.auth_scope == auth_scope,
            )
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if previous and previous["observed_at"] > observed_at:
        raise ProviderError("stale_balance_observation")
    if previous and previous["unit"] != unit:
        raise ProviderError("balance_unit_mismatch")
    if previous and cycle_started_at < previous["cycle_started_at"]:
        raise ProviderError("stale_balance_observation")
    if (
        previous
        and previous["renews_at"] != balance.renews_at
        and cycle_started_at == previous["cycle_started_at"]
    ):
        raise ProviderError("balance_cycle_required")
    if previous and previous["retain_until"] and previous["retain_until"] <= observed_at:
        previous = None
    if (
        previous
        and source_observation_id
        and previous["source_observation_id"] == source_observation_id
    ):
        return Decimal(0)
    if (
        previous
        and source_observation_id
        and previous["source_observation_id"]
        and previous["observed_at"] == observed_at
    ):
        raise ProviderError("stale_balance_observation")
    usage = credit_usage(connection, provider, auth_scope, unit)
    overlapping_usage = expected_usage is not None and expected_usage != usage
    total = balance.renewable + balance.additional
    difference = total - (
        previous["renewable_remaining"] + previous["additional_remaining"] if previous else total
    )
    same_cycle = previous is not None and (
        previous["cycle_started_at"] == cycle_started_at
        and previous["renews_at"] == balance.renews_at
    )
    consumed = usage - previous["confirmed_usage"] if previous else None
    connection.execute(
        balance_reconciliations.insert().values(
            provider=provider,
            auth_scope=auth_scope,
            unit=unit,
            observed_at=observed_at,
            retain_until=min(retain_until, previous["retain_until"] or retain_until)
            if previous
            else retain_until,
            kind="concurrent_usage"
            if overlapping_usage
            else "initial"
            if previous is None
            else "same_cycle"
            if same_cycle
            else "cycle_changed",
            balance_change=difference if previous else None,
            radar_consumption=consumed,
            unattributed_change=difference + consumed
            if same_cycle and consumed is not None and not overlapping_usage
            else None,
            source_observation_id=source_observation_id,
            previous_observation_id=previous["source_observation_id"] if previous else None,
        )
    )
    statement = pg_insert(credit_balances).values(
        provider=provider,
        auth_scope=auth_scope,
        renewable_remaining=balance.renewable,
        additional_remaining=balance.additional,
        renewable_allocation=balance.recurring_allocation,
        cycle_started_at=cycle_started_at,
        renews_at=balance.renews_at,
        observed_at=observed_at,
        refresh_required=overlapping_usage,
        unit=unit,
        confirmed_usage=usage,
        source_observation_id=source_observation_id,
        retain_until=retain_until,
    )
    connection.execute(
        statement.on_conflict_do_update(
            index_elements=["provider", "auth_scope"],
            set_={
                column.name: statement.excluded[column.name]
                for column in credit_balances.c
                if column.name not in {"id", "created_at", "provider", "auth_scope"}
            },
        )
    )
    return Decimal(difference)


def settle(
    connection: Connection,
    request_id: UUID,
    profile_id: UUID,
    actual: dict[str, Decimal] | None,
    now: datetime,
    *,
    not_sent: bool = False,
) -> None:
    lock_profile(connection, profile_id)
    request = (
        connection.execute(
            select(s.provider_requests)
            .where(s.provider_requests.c.id == request_id)
            .with_for_update()
        )
        .mappings()
        .one()
    )
    reservations = (
        connection.execute(
            select(s.cost_reservations)
            .where(s.cost_reservations.c.request_id == request_id)
            .with_for_update()
        )
        .mappings()
        .all()
    )
    if request["state"] in {"completed", "released"}:
        return
    lock_account(connection, request["provider"], request["auth_scope"])
    if not_sent and request["sent_at"] is not None:
        raise ProviderError("request_may_have_been_sent")
    if actual is not None and set(actual) != {row["unit"] for row in reservations}:
        raise ValueError("actual cost must specify every reserved unit")
    for row in reservations:
        status = "released" if not_sent else "unknown_charge" if actual is None else "confirmed"
        amount = row["amount"] if actual is None else actual[row["unit"]]
        if amount < 0:
            raise ValueError("negative actual cost")
        connection.execute(
            update(s.cost_reservations)
            .where(s.cost_reservations.c.id == row["id"])
            .values(status=status, amount=amount)
        )
        if status == "confirmed":
            connection.execute(
                insert(s.cost_ledger).values(
                    profile_id=profile_id,
                    request_id=request_id,
                    unit=row["unit"],
                    amount=amount,
                    kind="provider_usage",
                    external_reference=f"{request_id}:{row['unit']}",
                    occurred_at=now,
                )
            )
            if row["unit"].endswith("_credit") and amount > 0:
                # Refresh before further calls: bucket depletion order is provider-specific.
                connection.execute(
                    update(credit_balances)
                    .where(
                        credit_balances.c.provider == request["provider"],
                        credit_balances.c.auth_scope == request["auth_scope"],
                    )
                    .values(refresh_required=True)
                )
    connection.execute(
        update(s.provider_requests)
        .where(s.provider_requests.c.id == request_id)
        .values(
            state="released" if not_sent else "unknown_charge" if actual is None else "completed",
            completed_at=now if actual is not None or not_sent else None,
        )
    )
