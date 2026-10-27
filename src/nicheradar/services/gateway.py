import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, func, select

from nicheradar.domain.profile import CreatorProfile
from nicheradar.integrations.cache import cache_key, cached_batch, store_cache
from nicheradar.integrations.contracts import Batch, Cost, Operation, Provider, ProviderError
from nicheradar.integrations.policies import Usage, require_usage
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record
from nicheradar.repositories.schema import credit_balances
from nicheradar.services.budget import (
    Limits,
    balance_needs_refresh,
    credit_usage,
    lock_profile,
    reconcile_balance,
    reserve,
    settle,
)
from nicheradar.services.requests import mark_sent, prepare_request, record_not_sent


class Gateway:
    def __init__(
        self,
        engine: Engine,
        provider: Provider,
        profile_id: UUID,
        run_id: UUID,
        auth_scope: str,
        profile: CreatorProfile,
        limits: dict[str, Limits],
        tariffs: dict[Operation, tuple[Cost, ...]],
        *,
        scheduled: bool = False,
        maximum_calls: int = 20,
        credit_cycle_started_at: datetime | None = None,
    ):
        self.engine, self.provider = engine, provider
        self.profile_id, self.run_id = profile_id, run_id
        self.auth_scope, self.profile = auth_scope, profile
        self.limits, self.tariffs, self.scheduled = limits, tariffs, scheduled
        if maximum_calls < 1:
            raise ValueError("maximum_calls must be positive")
        self.maximum_calls = maximum_calls
        self.credit_cycle_started_at = credit_cycle_started_at

    async def fetch(
        self,
        operation: Operation,
        parameters: dict[str, Any],
        now: datetime,
        *,
        allow_external: bool = True,
    ) -> tuple[Batch, UUID, bool]:
        costs = self.tariffs.get(operation, ())
        metered = [cost for cost in costs if cost.unit.endswith("_credit") and cost.maximum != 0]
        if self.provider.name != "synthetic" and operation != Operation.BALANCE and metered:
            with self.engine.begin() as connection:
                # Do not refresh or spend merely to read cached research.
                hit = cached_batch(
                    connection,
                    cache_key(self.provider.name, operation, parameters, self.auth_scope),
                    now,
                )
                if hit is None and allow_external:
                    if any(cost.maximum is None for cost in costs):
                        raise ProviderError("unknown_cost")
                    for usage in (Usage.QUERY, Usage.STORAGE, Usage.HISTORY):
                        require_usage(
                            connection, self.provider.name, operation, usage, "metadata", now
                        )
                    if self.scheduled:
                        require_usage(
                            connection,
                            self.provider.name,
                            operation,
                            Usage.SCHEDULED,
                            "metadata",
                            now,
                        )
                current = (
                    connection.execute(
                        select(credit_balances).where(
                            credit_balances.c.provider == self.provider.name,
                            credit_balances.c.auth_scope == self.auth_scope,
                        )
                    )
                    .mappings()
                    .first()
                )
                checked_this_run = (
                    current is not None
                    and connection.execute(
                        select(s.raw_observations.c.id)
                        .join(
                            s.provider_requests,
                            s.provider_requests.c.id == s.raw_observations.c.request_id,
                        )
                        .where(
                            s.raw_observations.c.id == current["source_observation_id"],
                            s.provider_requests.c.run_id == self.run_id,
                        )
                    ).first()
                    is not None
                )
                refresh = not checked_this_run or balance_needs_refresh(
                    dict(current) if current else None, now
                )
            if hit is None and allow_external and refresh:
                tariff = self.tariffs.get(Operation.BALANCE, ())
                # Automatic balance queries require an explicitly verified free tariff.
                if (
                    Operation.BALANCE not in self.provider.operations
                    or not tariff
                    or any(cost.maximum != 0 for cost in tariff)
                ):
                    raise ProviderError("balance_refresh_required")
                await self.fetch(Operation.BALANCE, {}, now)
        if operation != Operation.BALANCE or self.provider.name == "synthetic":
            return await self._fetch(operation, parameters, now, allow_external=allow_external)
        units = {unit for unit in self.limits if unit.endswith("_credit")}
        if len(units) != 1:
            raise ProviderError("balance_unit_mismatch")
        unit = next(iter(units))
        with self.engine.connect() as connection:
            expected_usage = credit_usage(connection, self.provider.name, self.auth_scope, unit)
        batch, raw_id, cached = await self._fetch(
            operation, parameters, now, allow_external=allow_external
        )
        if (
            batch.balance is None
            or batch.provenance.provider != self.provider.name
            or batch.provenance.auth_scope != self.auth_scope
            or batch.provenance.operation != Operation.BALANCE
        ):
            raise ProviderError("balance_source_mismatch")
        with self.engine.begin() as connection:
            previous = (
                connection.execute(
                    select(credit_balances).where(
                        credit_balances.c.provider == self.provider.name,
                        credit_balances.c.auth_scope == self.auth_scope,
                    )
                )
                .mappings()
                .first()
            )
            start = batch.balance.cycle_started_at or self.credit_cycle_started_at
            if start is None and previous and previous["renews_at"] == batch.balance.renews_at:
                start = previous["cycle_started_at"]
            if start is None:
                raise ProviderError("balance_cycle_required")
            observed = batch.provenance.observed_at or batch.provenance.fetched_at
            if observed > now:
                raise ProviderError("stale_balance_observation")
            reconcile_balance(
                connection,
                self.profile_id,
                self.provider.name,
                self.auth_scope,
                batch.balance,
                observed,
                start,
                unit=unit,
                source_observation_id=raw_id,
                expected_usage=expected_usage,
            )
        return batch, raw_id, cached

    async def _fetch(
        self,
        operation: Operation,
        parameters: dict[str, Any],
        now: datetime,
        *,
        allow_external: bool = True,
    ) -> tuple[Batch, UUID, bool]:
        key = cache_key(self.provider.name, operation, parameters, self.auth_scope)
        synthetic = self.provider.name == "synthetic"
        with self.engine.begin() as connection:
            for usage in (Usage.STORAGE, Usage.HISTORY):
                require_usage(connection, self.provider.name, operation, usage, "metadata", now)
            # A historical balance response is never a fresh account check.
            hit = cached_batch(connection, key, now) if operation != Operation.BALANCE else None
            if hit:
                raw_id: UUID = connection.execute(
                    select(s.provider_cache.c.observation_id).where(
                        s.provider_cache.c.cache_key == key
                    )
                ).scalar_one()
                return hit, raw_id, True
            if not allow_external:
                raise ProviderError("batch_limit")
            lock_profile(connection, self.profile_id)
            attempts = connection.execute(
                select(func.count())
                .select_from(s.provider_requests)
                .where(
                    s.provider_requests.c.run_id == self.run_id,
                    # The cap is per provider: classification (openai) shares the analysis run
                    # with channel verification (youtube) and must not exhaust its calls.
                    s.provider_requests.c.provider == self.provider.name,
                    (s.provider_requests.c.sent_at.is_not(None))
                    | (
                        (s.provider_requests.c.state == "prepared")
                        & ~(
                            (s.provider_requests.c.provider == self.provider.name)
                            & (s.provider_requests.c.auth_scope == self.auth_scope)
                            & (s.provider_requests.c.cache_key == key)
                        )
                    ),
                )
            ).scalar_one()
            if attempts >= self.maximum_calls:
                raise ProviderError("batch_limit")
            require_usage(connection, self.provider.name, operation, Usage.QUERY, "metadata", now)
            if self.scheduled:
                require_usage(
                    connection, self.provider.name, operation, Usage.SCHEDULED, "metadata", now
                )
            unresolved = connection.execute(
                select(s.provider_requests.c.id)
                .where(
                    s.provider_requests.c.provider == self.provider.name,
                    s.provider_requests.c.auth_scope == self.auth_scope,
                    s.provider_requests.c.cache_key == key,
                    s.provider_requests.c.state.in_(["sent", "unknown_charge"]),
                )
                .limit(1)
            ).first()
            if unresolved:
                raise ProviderError("unknown_charge")
            if not synthetic and not self.profile.paid_limits_confirmed:
                raise ProviderError("budget_confirmation_required")
            policy = require_usage(
                connection, self.provider.name, operation, Usage.STORAGE, "metadata", now
            )
            retention_seconds = 7 * 86400
            if policy:
                retention_seconds = connection.execute(
                    select(s.provider_policies.c.retention_seconds).where(
                        s.provider_policies.c.id == policy
                    )
                ).scalar_one()
                if not retention_seconds:
                    raise ProviderError("retention_not_configured")
            else:
                policy = insert_record(
                    connection,
                    "provider_policies",
                    {
                        "provider": "synthetic",
                        "operation": operation.value,
                        "data_type": "metadata",
                        "usage": "storage",
                        "version": str(uuid.uuid4()),
                        "status": "enabled",
                        "evidence_source": "own synthetic data",
                        "effective_at": now,
                        "retention_seconds": retention_seconds,
                    },
                )
            # Keep each certified-unsent attempt auditable. An unresolved attempt never
            # permits this increment; its unique outstanding request still blocks a send.
            unsent_attempts = connection.execute(
                select(func.count())
                .select_from(s.provider_requests)
                .where(
                    s.provider_requests.c.run_id == self.run_id,
                    s.provider_requests.c.provider == self.provider.name,
                    s.provider_requests.c.auth_scope == self.auth_scope,
                    s.provider_requests.c.cache_key == key,
                    (s.provider_requests.c.state == "released")
                    & (s.provider_requests.c.error_code == "transport_not_sent")
                    | (
                        (s.provider_requests.c.state == "completed")
                        if operation == Operation.BALANCE
                        else False
                    ),
                )
            ).scalar_one()
            attempt_key = f"{self.run_id}:{key}" + (
                f":retry:{unsent_attempts}" if unsent_attempts else ""
            )
            request_id = prepare_request(
                connection,
                self.run_id,
                self.provider.name,
                operation,
                self.auth_scope,
                key,
                attempt_key,
                now,
            )
            costs = (
                (Cost(unit="USD", maximum=Decimal(0), source="synthetic"),)
                if synthetic
                else self.tariffs.get(operation, ())
            )
            if not costs:
                raise ProviderError("unknown_cost")
            limits = (
                {
                    "USD": Limits(
                        operation=Decimal(0), run=Decimal(0), week=Decimal(0), period=Decimal(0)
                    )
                }
                if synthetic
                else self.limits
            )
            existing = connection.execute(
                select(s.cost_reservations.c.id).where(
                    s.cost_reservations.c.request_id == request_id,
                    s.cost_reservations.c.status == "reserved",
                )
            ).first()
            if existing is None:
                reserve(connection, request_id, self.profile_id, costs, limits, now)
        with self.engine.begin() as connection:
            mark_sent(connection, request_id, now)
        try:
            batch = await self.provider.fetch(operation, parameters, now)
        except ProviderError as error:
            with self.engine.begin() as connection:
                if error.not_sent:
                    record_not_sent(connection, request_id, self.profile_id, now)
                else:
                    settle(connection, request_id, self.profile_id, None, now)
            if error.not_sent:
                raise
            # A safe-retry hint is insufficient after a possibly sent request.
            raise ProviderError(error.code, may_have_charged=True) from None
        except Exception:
            with self.engine.begin() as connection:
                settle(connection, request_id, self.profile_id, None, now)
            raise
        with self.engine.begin() as connection:
            # Actual amounts must be returned by the adapter; unknown real charge stays reserved.
            actual = {cost.unit: cost.actual for cost in batch.costs}
            known = set(actual) == {cost.unit for cost in costs} and all(
                value is not None for value in actual.values()
            )
            settle(
                connection,
                request_id,
                self.profile_id,
                {unit: value for unit, value in actual.items() if value is not None}
                if known
                else None,
                now,
            )
            raw_id = insert_record(
                connection,
                "raw_observations",
                {
                    "request_id": request_id,
                    "policy_id": policy,
                    "normalization_version": batch.provenance.normalization_version,
                    "fetched_at": batch.provenance.fetched_at,
                    "observed_at": batch.provenance.observed_at,
                    "retain_until": now + timedelta(seconds=retention_seconds),
                    "payload": batch.model_dump(mode="json"),
                    "coverage": batch.coverage.model_dump(mode="json"),
                },
            )
            store_cache(
                connection, key, raw_id, now + timedelta(seconds=min(86400, retention_seconds))
            )
        return batch, raw_id, False
