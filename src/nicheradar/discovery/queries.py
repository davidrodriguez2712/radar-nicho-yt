"""Bounded query expansion and durable receipts; no provider text in job checkpoints."""

import hashlib
import json
from collections.abc import Callable
from datetime import datetime
from itertools import zip_longest
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, func, select, update

from nicheradar.domain.profile import CreatorProfile, VideoFormat
from nicheradar.integrations.cache import cache_key
from nicheradar.integrations.contracts import Batch, Operation, ProviderError
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record
from nicheradar.services.gateway import Gateway
from nicheradar.workers.queue import confirm_stage, heartbeat, owned_job

PARTIAL_REASONS = {
    "batch_limit",
    "run_budget_exhausted",
    "period_budget_exhausted",
    "shared_budget_exhausted",
    "balance_exhausted",
    "unknown_cost",
}


async def collect(
    engine: Engine,
    gateway: Gateway,
    job: dict[str, Any],
    owner: str,
    profile: CreatorProfile,
    clock: Callable[[], datetime],
    maximum_calls: int,
) -> None:
    plan = job["checkpoints"]["planning"]
    scope = hashlib.sha256(
        json.dumps(
            {
                "language": profile.language,
                "formats": profile.formats,
                "channels": profile.discovery_max_channels,
                "expansions": profile.discovery_max_expansions,
                "small_threshold": profile.small_channel_subscribers,
                "query": plan["query"],
                "topic": plan.get("target_topic_id"),
                "format": plan.get("target_format"),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    saved = job["checkpoints"]
    if not saved.get("query_receipts_v2") and plan.get("source_job_id"):
        with engine.connect() as connection:
            saved = connection.execute(
                select(s.jobs.c.checkpoints).where(s.jobs.c.id == UUID(plan["source_job_id"]))
            ).scalar_one()
    receipts: dict[str, str] = (
        dict(saved.get("query_receipts_v2", {})) if saved.get("query_scope_v1") == scope else {}
    )
    used: set[str] = set()

    async def fetch(key: str, operation: Operation, params: dict[str, Any]) -> tuple[Batch, str]:
        used.add(key)
        with engine.begin() as connection:
            heartbeat(connection, job["id"], owner, clock())
            if key in receipts:
                payload = connection.execute(
                    select(s.raw_observations.c.payload).where(
                        s.raw_observations.c.id == UUID(receipts[key]),
                        s.raw_observations.c.retain_until > clock(),
                        s.raw_observations.c.request_id.in_(
                            select(s.provider_requests.c.id).where(
                                s.provider_requests.c.cache_key
                                == cache_key(
                                    gateway.provider.name, operation, params, gateway.auth_scope
                                )
                            )
                        ),
                    )
                ).scalar_one_or_none()
                if payload is not None:
                    return Batch.model_validate(payload), receipts[key]
                del receipts[key]
            sent = connection.execute(
                select(func.count())
                .select_from(s.provider_requests)
                .where(
                    s.provider_requests.c.run_id == job["run_id"],
                    s.provider_requests.c.sent_at.is_not(None),
                )
            ).scalar_one()
        batch, raw_id, _ = await gateway.fetch(
            operation, params, clock(), allow_external=sent < maximum_calls
        )
        receipts[key] = str(raw_id)
        with engine.begin() as connection:
            current = owned_job(connection, job["id"], owner, clock())
            connection.execute(
                update(s.jobs)
                .where(s.jobs.c.id == job["id"])
                .values(
                    checkpoints=current["checkpoints"]
                    | {
                        "query_receipts_v2": receipts,
                        "query_scope_v1": scope,
                    }
                )
            )
        return batch, str(raw_id)

    complete, reason = True, None
    try:
        channels: dict[str, None] = {}
        channel_pools: list[list[str]] = []
        roots: list[tuple[Batch, str]] = []
        if plan.get("target_topic_id"):
            with engine.connect() as connection:
                channels = dict.fromkeys(
                    connection.execute(
                        select(s.channels.c.external_id)
                        .join(s.videos, s.videos.c.channel_id == s.channels.c.id)
                        .join(s.topic_memberships, s.topic_memberships.c.video_id == s.videos.c.id)
                        .where(s.topic_memberships.c.topic_id == UUID(plan["target_topic_id"]))
                        .distinct()
                        .order_by(s.channels.c.external_id)
                        .limit(profile.discovery_max_channels)
                    ).scalars()
                )
        if not channels:
            for index, size in enumerate(
                (
                    {"subscriberCountMax": profile.small_channel_subscribers},
                    {"subscriberCountMin": profile.small_channel_subscribers + 1},
                )
            ):
                batch, raw_id = await fetch(
                    f"root:{index}",
                    Operation.CHANNEL_SEARCH,
                    {
                        "query": plan["query"],
                        "family": plan["family_key"],
                        "languages": [profile.language],
                        "limit": profile.discovery_max_channels,
                        **size,
                    },
                )
                roots.append((batch, raw_id))
                channel_pools.append([channel.id for channel in batch.channels])
        if plan["kind"] == "catalog":
            expansions = []
            seen = {plan["query"].casefold()}
            for batch, raw_id in roots:
                for channel_index, channel in enumerate(batch.channels):
                    # The originating channel must support the family, not merely a keyword hit.
                    if channel.category != plan["family_key"]:
                        continue
                    for topic_index, topic in enumerate(channel.subtopics):
                        term = " ".join(topic.split())
                        if not 2 <= len(term) <= 120 or term.casefold() in seen:
                            continue
                        seen.add(term.casefold())
                        expansions.append((term, raw_id, channel_index, topic_index))
            for term, raw_id, channel_index, topic_index in expansions[
                : profile.discovery_max_expansions
            ]:
                reference = f"evidence:{raw_id}:channel:{channel_index}:subtopic:{topic_index}"
                with engine.begin() as connection:
                    owned_job(connection, job["id"], owner, clock())
                    existing = connection.execute(
                        select(s.discovery_queries.c.id).where(
                            s.discovery_queries.c.run_id == job["run_id"],
                            s.discovery_queries.c.query == reference,
                        )
                    ).first()
                    if not existing:
                        insert_record(
                            connection,
                            "discovery_queries",
                            {
                                "run_id": job["run_id"],
                                "family_id": UUID(plan["family_id"]),
                                "parent_query_id": UUID(plan["query_id"]),
                                "query": reference,
                                "selection_method": "provider_subtopic_expansion",
                                "created_at": clock(),
                            },
                        )
                key = "expansion:" + hashlib.sha256(term.casefold().encode()).hexdigest()
                batch, _ = await fetch(
                    key,
                    Operation.CHANNEL_SEARCH,
                    {
                        "query": term,
                        "family": plan["family_key"],
                        "languages": [profile.language],
                        "limit": profile.discovery_max_channels,
                    },
                )
                channel_pools.append([channel.id for channel in batch.channels])
        formats = (
            (VideoFormat(plan["target_format"]),) if plan.get("target_format") else profile.formats
        )
        # Interleave size strata and expansions before capping, so the first pool
        # cannot consume the entire sample when a provider fills every result page.
        for row in zip_longest(*channel_pools):
            channels.update(dict.fromkeys(channel_id for channel_id in row if channel_id))
        for channel_id in list(channels)[: profile.discovery_max_channels]:
            for format in formats:
                await fetch(
                    f"recent:{channel_id}:{format}",
                    Operation.CHANNEL_VIDEOS,
                    {
                        "channelId": channel_id,
                        "family": plan["family_key"],
                        "videoFormat": "short" if format == VideoFormat.SHORTS else "long",
                        "popular": False,
                    },
                )
        if plan["kind"] == "catalog":
            for format in formats:
                await fetch(
                    f"outliers:{format}",
                    Operation.OUTLIERS,
                    {
                        "query": plan["query"],
                        "family": plan["family_key"],
                        "videoFormat": "short" if format == VideoFormat.SHORTS else "long",
                    },
                )
    except ProviderError as error:
        if error.code not in PARTIAL_REASONS:
            raise
        complete, reason = False, error.code
    with engine.begin() as connection:
        current = owned_job(connection, job["id"], owner, clock())
        retained = set(
            str(value)
            for value in connection.execute(
                select(s.raw_observations.c.id).where(
                    s.raw_observations.c.id.in_([UUID(value) for value in receipts.values()]),
                    s.raw_observations.c.retain_until > clock(),
                )
            ).scalars()
        )
        receipts = {key: value for key, value in receipts.items() if value in retained}
        connection.execute(
            update(s.jobs)
            .where(s.jobs.c.id == job["id"])
            .values(
                checkpoints=current["checkpoints"]
                | {
                    "query_receipts_v2": receipts,
                    "query_scope_v1": scope,
                }
            )
        )
        confirm_stage(
            connection,
            job["id"],
            owner,
            clock(),
            "query",
            {
                "raw_ids": sorted({value for key, value in receipts.items() if key in used}),
                "complete": complete,
                "reason": reason,
            },
        )
