# src/nicheradar/market_intel/verification.py
"""Contrast seller-declared subscribers with YouTube for the highest-income listings.

A mismatch or a missing channel removes the listing's income from the niche statistics; an
unverifiable one (hidden count, unsupported URL) stays neutral and is never counted as verified.
"""

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, or_, select

from nicheradar.discovery.channel_analysis import resolve_channel
from nicheradar.integrations.contracts import Channel, ProviderError
from nicheradar.market_intel.classify import PROMPT_VERSION
from nicheradar.market_intel.context import RunContext
from nicheradar.market_intel.ingest import LISTING_RETENTION
from nicheradar.market_intel.scoring import SUBS_MISMATCH_TOLERANCE
from nicheradar.repositories.core import get_profile
from nicheradar.repositories.schema import listing_classifications as lc
from nicheradar.repositories.schema import listing_verifications as lv
from nicheradar.repositories.schema import marketplace_listings as ml
from nicheradar.services.channel_analysis_providers import (
    channel_analysis_youtube_limits,
    channel_analysis_youtube_tariffs,
)
from nicheradar.services.gateway import Gateway
from nicheradar.services.youtube_enrichment import youtube_provider

VERIFICATION_TTL = timedelta(days=30)
Resolver = Callable[[str], Awaitable[Channel]]


def verification_status(declared: int | None, real: int | None) -> str:
    if real is None:
        return "unverifiable"
    if declared is None:
        return "verified"
    gap = abs(declared - real) / max(real, 1)
    return "mismatch" if gap > SUBS_MISMATCH_TOLERANCE else "verified"


def pending_verification(
    connection: Connection, source: str, limit: int, now: datetime
) -> list[dict[str, Any]]:
    recent = select(lv.c.listing_id).where(lv.c.checked_at >= now - VERIFICATION_TTL)
    rows = connection.execute(
        select(ml.c.id, ml.c.channel_url, ml.c.subscribers, ml.c.youtube_channel_id)
        .select_from(
            ml.join(lc, (lc.c.listing_id == ml.c.id) & (lc.c.prompt_version == PROMPT_VERSION))
        )
        .where(
            ml.c.source == source,
            ml.c.status == "active",
            ml.c.income_monthly_usd > 0,
            ml.c.channel_url.is_not(None),
            or_(lc.c.niche_label.is_not(None), lc.c.other_label.is_not(None)),
            ml.c.id.not_in(recent),
        )
        .order_by(ml.c.income_monthly_usd.desc(), ml.c.external_id.desc())
        .limit(limit)
    ).mappings()
    return [dict(row) for row in rows]


def save_verification(
    connection: Connection,
    listing_id: UUID,
    youtube_channel_id: str | None,
    real_subscribers: int | None,
    status: str,
    now: datetime,
) -> None:
    connection.execute(
        lv.insert().values(
            id=uuid4(),
            listing_id=listing_id,
            youtube_channel_id=youtube_channel_id,
            real_subscribers=real_subscribers,
            status=status,
            checked_at=now,
            retain_until=now + LISTING_RETENTION,
        )
    )


def build_resolver(ctx: RunContext) -> Resolver:
    """Raises ProviderError when YouTube is not configured; the Gateway enforces quota/policy."""
    config = ctx.config
    youtube = youtube_provider(config)
    with ctx.engine.connect() as connection:
        profile_id, _, profile = get_profile(connection)
    gateway = Gateway(
        ctx.engine,
        youtube,
        profile_id,
        ctx.analysis_run["id"],
        str(config.youtube_auth_scope),
        profile,
        channel_analysis_youtube_limits(config),
        channel_analysis_youtube_tariffs(),
        maximum_calls=max(1, config.market_intel_verify_cap_per_run),
    )

    async def resolve(channel_url: str) -> Channel:
        return await resolve_channel(gateway, channel_url, ctx.clock())

    return resolve


async def _verify(
    ctx: RunContext, pending: list[dict[str, Any]], resolve: Resolver
) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    stopped: str | None = None
    for item in pending:
        channel: Channel | None = None
        try:
            channel = await resolve(item["channel_url"])
            status = verification_status(item["subscribers"], channel.subscribers)
        except ValueError:
            status = "unverifiable"  # a URL form the YouTube resolver does not accept
        except ProviderError as error:
            if error.code != "channel_not_found":
                stopped = error.code
                break
            status = "not_found"
        with ctx.engine.begin() as connection:
            save_verification(
                connection,
                item["id"],
                channel.id if channel else item["youtube_channel_id"],
                channel.subscribers if channel else None,
                status,
                ctx.clock(),
            )
        counts[status] += 1
    result: dict[str, Any] = {"checked": sum(counts.values()), **counts}
    if stopped is not None:
        result |= {"stopped_reason": stopped, "partial": True}
    return result


def stage_verify(ctx: RunContext, resolver: Resolver | None = None) -> dict[str, Any]:
    config = ctx.config
    if ctx.analysis_run["mode"] != "live":
        return {"skipped": "synthetic_mode"}
    if config.market_intel_verify_cap_per_run == 0 or not config.youtube_live_enabled:
        return {"skipped": "youtube_not_enabled"}
    with ctx.engine.connect() as connection:
        pending = pending_verification(
            connection, ctx.source.name, config.market_intel_verify_cap_per_run, ctx.clock()
        )
    if not pending:
        return {"checked": 0}
    try:
        resolve = resolver or build_resolver(ctx)
    except ProviderError as error:
        return {"skipped": error.code, "partial": True}
    return asyncio.run(_verify(ctx, pending, resolve))
