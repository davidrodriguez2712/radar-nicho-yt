"""Paid-request state machine. Every transition commits before external work."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Connection, select, update
from sqlalchemy.dialects.postgresql import insert

from nicheradar.integrations.contracts import Operation, ProviderError
from nicheradar.repositories import schema_v1 as s
from nicheradar.services.budget import lock_profile, validate_reserved_balance


def prepare_request(
    connection: Connection,
    run_id: UUID,
    provider: str,
    operation: Operation,
    auth_scope: str,
    key: str,
    idempotency_key: str,
    now: datetime,
) -> UUID:
    connection.execute(
        insert(s.provider_requests)
        .values(
            run_id=run_id,
            provider=provider,
            operation=operation.value,
            auth_scope=auth_scope,
            cache_key=key,
            idempotency_key=idempotency_key,
            state="prepared",
            created_at=now,
        )
        .on_conflict_do_nothing()
    )
    row = (
        connection.execute(
            select(s.provider_requests).where(
                s.provider_requests.c.idempotency_key == idempotency_key
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise ProviderError("request_in_progress")
    if any(
        row[field] != value
        for field, value in {
            "run_id": run_id,
            "provider": provider,
            "operation": operation.value,
            "auth_scope": auth_scope,
            "cache_key": key,
        }.items()
    ):
        raise ProviderError("idempotency_conflict")
    return UUID(str(row["id"]))


def mark_sent(connection: Connection, request_id: UUID, now: datetime) -> None:
    profile_id = connection.execute(
        select(s.analysis_runs.c.profile_id)
        .join(s.provider_requests, s.provider_requests.c.run_id == s.analysis_runs.c.id)
        .where(s.provider_requests.c.id == request_id)
    ).scalar_one()
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
    if request["state"] != "prepared" or request["sent_at"] is not None:
        raise ProviderError("request_requires_reconciliation")
    reserved = connection.execute(
        select(s.cost_reservations.c.id).where(
            s.cost_reservations.c.request_id == request_id,
            s.cost_reservations.c.status == "reserved",
        )
    ).first()
    if reserved is None:
        raise ProviderError("request_not_reserved")
    validate_reserved_balance(connection, request_id, now)
    # Commit this state before handing control to a transport. If the process dies
    # even just before transmission, remain conservative and reconcile before retry.
    connection.execute(
        update(s.provider_requests)
        .where(s.provider_requests.c.id == request_id)
        .values(state="sent", sent_at=now)
    )


def recover_uncertain_requests(connection: Connection, run_id: UUID) -> int:
    ids = list(
        connection.execute(
            select(s.provider_requests.c.id)
            .where(s.provider_requests.c.run_id == run_id, s.provider_requests.c.state == "sent")
            .with_for_update()
        ).scalars()
    )
    if ids:
        connection.execute(
            update(s.provider_requests)
            .where(s.provider_requests.c.id.in_(ids))
            .values(state="unknown_charge")
        )
        connection.execute(
            update(s.cost_reservations)
            .where(
                s.cost_reservations.c.request_id.in_(ids),
                s.cost_reservations.c.status == "reserved",
            )
            .values(status="unknown_charge")
        )
    return len(ids)


def record_not_sent(
    connection: Connection, request_id: UUID, profile_id: UUID, now: datetime
) -> None:
    """Release only after an explicit unsent transport result, retaining dispatch intent/time.

    Never use for timeouts, cancellation, process death or ambiguous responses.
    A retry creates a new attempt receipt rather than rewriting this audit record.
    """
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
    if request["state"] != "sent":
        raise ProviderError("request_requires_reconciliation")
    connection.execute(
        update(s.cost_reservations)
        .where(
            s.cost_reservations.c.request_id == request_id,
            s.cost_reservations.c.status == "reserved",
        )
        .values(status="released")
    )
    connection.execute(
        update(s.provider_requests)
        .where(s.provider_requests.c.id == request_id)
        .values(state="released", error_code="transport_not_sent", completed_at=now)
    )
