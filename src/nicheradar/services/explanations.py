"""Optional enrichment with durable reservations, terminal fallback and retained lineage."""

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import Connection, Engine, select, update

from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile
from nicheradar.integrations.cache import cache_key
from nicheradar.integrations.contracts import Cost, Operation, ProviderError
from nicheradar.integrations.llm import OpenAISelector, request_body
from nicheradar.integrations.policies import Usage, require_usage
from nicheradar.integrations.retention import expire
from nicheradar.recommendations.explanations import Explanation, reorder
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record
from nicheradar.services.budget import lock_profile, reserve, settle
from nicheradar.services.requests import mark_sent, prepare_request


def source_permissions(connection: Connection, evaluation_id: UUID, now: datetime) -> None:
    sources = connection.execute(
        select(
            s.provider_requests.c.provider,
            s.provider_requests.c.operation,
            s.provider_policies.c.data_type,
        )
        .select_from(s.evidence_links)
        .join(s.raw_observations, s.raw_observations.c.id == s.evidence_links.c.observation_id)
        .join(s.provider_requests, s.provider_requests.c.id == s.raw_observations.c.request_id)
        .join(s.provider_policies, s.provider_policies.c.id == s.raw_observations.c.policy_id)
        .where(s.evidence_links.c.evaluation_id == evaluation_id)
    ).all()
    if not sources:
        raise ProviderError("llm_no_evidence")
    for source in sources:
        require_usage(
            connection,
            source.provider,
            Operation(source.operation),
            Usage.LLM_PROCESSING,
            source.data_type,
            now,
        )


async def enrich(
    engine: Engine,
    evaluation_id: UUID,
    config: Settings,
    clock: Callable[[], datetime],
    *,
    selector: OpenAISelector | None = None,
) -> None:
    """Called after deterministic evaluation commits, outside a worker DB transaction."""
    now = clock()
    with engine.begin() as connection:
        expire(connection, now)
        evaluation = (
            connection.execute(
                select(s.evaluation_versions).where(s.evaluation_versions.c.id == evaluation_id)
            )
            .mappings()
            .one()
        )
        if not evaluation["explanation"] or evaluation["expired_at"]:
            return
        snapshot = evaluation["explanation"]
        if "narrative" not in snapshot:
            return
        narrative = Explanation.model_validate(snapshot["narrative"])
        if narrative.enrichment not in {"pending", "processing"}:
            return
        run = (
            connection.execute(
                select(s.analysis_runs).where(s.analysis_runs.c.id == evaluation["run_id"])
            )
            .mappings()
            .one()
        )
    configuration = config.llm_configuration
    request_id = None
    policy_id = None
    deadline = evaluation["retain_until"]
    reason = "disabled"
    body = None
    if narrative.enrichment == "processing":
        # Recovery never resends a committed attempt, even after settings or account changes.
        with engine.begin() as connection:
            request_id = connection.execute(
                select(s.provider_requests.c.id).where(
                    s.provider_requests.c.idempotency_key == f"explanation:{evaluation_id}"
                )
            ).scalar_one_or_none()
            if request_id:
                settle(connection, request_id, run["profile_id"], None, now)
        reason = "llm_prior_attempt_requires_review"
    elif config.llm_enabled and run["mode"] != "live":
        reason = "synthetic_mode"
    elif config.llm_enabled and (configuration is None or config.llm_api_key is None):
        reason = "configuration_missing"
    elif config.llm_enabled and configuration and config.llm_api_key:
        try:
            tariff = configuration.tariff
            if not tariff.verified_at <= now < tariff.valid_until:
                raise ProviderError("llm_tariff_not_current")
            body = request_body(narrative, tariff)
            with engine.begin() as connection:
                lock_profile(connection, run["profile_id"])
                current = (
                    connection.execute(
                        select(s.evaluation_versions)
                        .where(s.evaluation_versions.c.id == evaluation_id)
                        .with_for_update()
                    )
                    .mappings()
                    .one()
                )
                if (
                    current["expired_at"]
                    or current["retain_until"] <= clock()
                    or not current["explanation"]
                ):
                    return
                if current["explanation"]["narrative"]["enrichment"] not in {
                    "pending",
                    "processing",
                }:
                    return
                profile = CreatorProfile.model_validate(
                    connection.execute(
                        select(s.creator_profiles.c.configuration).where(
                            s.creator_profiles.c.id == run["profile_id"]
                        )
                    ).scalar_one()
                )
                if not profile.paid_limits_confirmed:
                    raise ProviderError("budget_confirmation_required")
                for usage in (Usage.QUERY, Usage.STORAGE, Usage.DERIVED, Usage.LLM_PROCESSING):
                    policy = require_usage(
                        connection, "openai", Operation.EXPLANATION, usage, "explanation", clock()
                    )
                    if usage == Usage.STORAGE:
                        policy_id = policy
                if run["trigger"] == "scheduled":
                    require_usage(
                        connection,
                        "openai",
                        Operation.EXPLANATION,
                        Usage.SCHEDULED,
                        "explanation",
                        clock(),
                    )
                source_permissions(connection, evaluation_id, clock())
                seconds = connection.execute(
                    select(s.provider_policies.c.retention_seconds).where(
                        s.provider_policies.c.id == policy_id
                    )
                ).scalar_one()
                if not seconds:
                    raise ProviderError("retention_not_configured")
                deadline = min(deadline, now + timedelta(seconds=seconds))
                unresolved = connection.execute(
                    select(s.provider_requests.c.id).where(
                        s.provider_requests.c.provider == "openai",
                        s.provider_requests.c.auth_scope == configuration.auth_scope,
                        s.provider_requests.c.state.in_(["sent", "unknown_charge"]),
                    )
                ).first()
                if unresolved:
                    raise ProviderError("unknown_charge")
                key = cache_key(
                    "openai",
                    Operation.EXPLANATION,
                    {"evaluation_id": str(evaluation_id)},
                    configuration.auth_scope,
                    "explanation-v2",
                )
                request_id = prepare_request(
                    connection,
                    run["id"],
                    "openai",
                    Operation.EXPLANATION,
                    configuration.auth_scope,
                    key,
                    f"explanation:{evaluation_id}",
                    now,
                )
                # A prior committed result (or ambiguous send) never triggers another call.
                state = connection.execute(
                    select(s.provider_requests.c.state).where(
                        s.provider_requests.c.id == request_id
                    )
                ).scalar_one()
                if state != "prepared":
                    raise ProviderError("llm_already_attempted")
                reserve(
                    connection,
                    request_id,
                    run["profile_id"],
                    (Cost(unit="USD", maximum=tariff.maximum_usd(), source=tariff.source),),
                    {"USD": configuration.limits},
                    now,
                    config.timezone,
                )
                mark_sent(connection, request_id, now)
                processing = narrative.model_copy(update={"enrichment": "processing"})
                connection.execute(
                    update(s.evaluation_versions)
                    .where(s.evaluation_versions.c.id == evaluation_id)
                    .values(
                        explanation=current["explanation"]
                        | {
                            "narrative": processing.model_dump(mode="json"),
                            "enrichment": {"tariff": tariff.model_dump(mode="json")},
                        },
                        retain_until=deadline,
                    )
                )
            # Reservation and sent marker committed before transport. No retry even on 401/429.
            try:
                client = selector or OpenAISelector(config.llm_api_key)
                result = await asyncio.wait_for(
                    client.select(body, configuration), timeout=configuration.timeout_seconds
                )
                with engine.begin() as connection:
                    settle(
                        connection,
                        request_id,
                        run["profile_id"],
                        {"USD": result.actual_usd} if result.actual_usd is not None else None,
                        clock(),
                    )
                reason = result.reason if result.actual_usd is not None else "unknown_charge"
                if result.order is not None and result.actual_usd is not None:
                    narrative = reorder(narrative, list(result.order))
                    reason = "validated_order"
            except Exception:
                with engine.begin() as connection:
                    settle(connection, request_id, run["profile_id"], None, clock())
                reason = "llm_failed_or_invalid_order"
        except ProviderError as error:
            reason = error.code
            if request_id:
                with engine.connect() as connection:
                    if (
                        connection.execute(
                            select(s.provider_requests.c.id).where(
                                s.provider_requests.c.id == request_id
                            )
                        ).first()
                        is None
                    ):
                        request_id = None
    with engine.begin() as connection:
        expire(connection, clock())
        current = (
            connection.execute(
                select(s.evaluation_versions)
                .where(s.evaluation_versions.c.id == evaluation_id)
                .with_for_update()
            )
            .mappings()
            .one()
        )
        if (
            current["expired_at"]
            or current["retain_until"] <= clock()
            or not current["explanation"]
        ):
            return
        if current["explanation"]["narrative"]["enrichment"] not in {"pending", "processing"}:
            return
        if narrative.enrichment == "llm_emphasis_only":
            try:
                for usage in (Usage.STORAGE, Usage.DERIVED, Usage.LLM_PROCESSING):
                    require_usage(
                        connection, "openai", Operation.EXPLANATION, usage, "explanation", clock()
                    )
                source_permissions(connection, evaluation_id, clock())
            except ProviderError:
                narrative = Explanation.model_validate(snapshot["narrative"])
                reason = "policy_changed_during_call"
        if narrative.enrichment != "llm_emphasis_only":
            narrative = narrative.model_copy(
                update={
                    "enrichment": "deterministic_fallback"
                    if config.llm_enabled
                    else "deterministic"
                }
            )
        elif request_id and policy_id:
            raw_id = insert_record(
                connection,
                "raw_observations",
                {
                    "request_id": request_id,
                    "policy_id": policy_id,
                    "normalization_version": "explanation-order-v1",
                    "fetched_at": clock(),
                    "retain_until": current["retain_until"],
                    "payload": {"order": [claim.key for claim in narrative.claims]},
                    "coverage": {"selection_method": "validated_claim_order"},
                },
            )
            insert_record(
                connection,
                "evidence_links",
                {
                    "evaluation_id": evaluation_id,
                    "observation_id": raw_id,
                    "availability": "available",
                    "claim_key": "explanation_order",
                    "retain_until": current["retain_until"],
                },
            )
        connection.execute(
            update(s.evaluation_versions)
            .where(s.evaluation_versions.c.id == evaluation_id)
            .values(
                explanation=current["explanation"]
                | {
                    "narrative": narrative.model_dump(mode="json"),
                    "enrichment": {
                        "method_version": "explanation-v2",
                        "cost_basis": "reported_usage_times_configured_tariff_not_invoice",
                        "reason": reason,
                        "request_id": str(request_id) if request_id else None,
                        "tariff": current["explanation"].get("enrichment", {}).get("tariff"),
                    },
                }
            )
        )
