# src/nicheradar/market_intel/evidence_stage.py
"""Read the screenshots sellers attach to a listing (listing-evidence-v1, docs/contracts).

Per listing: fetch the page for its attachments, download them in memory (never stored; only
their SHA-256 is kept), one bounded vision call, validate, derive, save. Everything the seller
attached is untrusted data. A listing is revisited only when the prompt or schema version changes.
"""

import asyncio
import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx
from sqlalchemy import Connection, Engine, case, select

from nicheradar.config import Settings
from nicheradar.integrations.cache import cache_key
from nicheradar.integrations.contracts import Cost, Operation, ProviderError
from nicheradar.integrations.llm import OpenAISelector
from nicheradar.integrations.policies import Usage, require_usage
from nicheradar.market_intel.context import RunContext
from nicheradar.market_intel.contracts import SourceError
from nicheradar.market_intel.evidence.summary import build_derived
from nicheradar.market_intel.evidence.wire import (
    PROMPT_VERSION,
    EvidenceResult,
    parse_response,
    request_body,
)
from nicheradar.market_intel.ingest import LISTING_RETENTION
from nicheradar.repositories.schema import listing_channel_snapshots as snapshots
from nicheradar.repositories.schema import listing_evidence as le
from nicheradar.repositories.schema import marketplace_listings as ml
from nicheradar.services.budget import reserve, settle
from nicheradar.services.requests import mark_sent, prepare_request

SCHEMA_VERSION = "listing-evidence-v1"
POLICY_DATA_TYPE = "market_listing_evidence"
MAX_IMAGES = 12
MAX_IMAGE_BYTES = 6_000_000
MAX_BODY_BYTES = 40_000_000
VISION_TIMEOUT_SECONDS = 120
IMAGE_HOSTS = frozenset({"media.dealbaron.com"})
IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
CONSECUTIVE_FAILURES_STOP = 3
# Declines that blame one listing's request, not the whole stage.
LISTING_LEVEL_DECLINES = frozenset({"request_in_progress", "idempotency_conflict"})


@dataclass(frozen=True)
class Downloaded:
    data: bytes
    mime: str
    sha256: str


def pending_evidence(
    connection: Connection, source: str, limit: int, now: datetime
) -> list[dict[str, Any]]:
    done = select(le.c.listing_id).where(
        le.c.prompt_version == PROMPT_VERSION, le.c.schema_version == SCHEMA_VERSION
    )
    api_title = (
        select(snapshots.c.title)
        .where(snapshots.c.listing_id == ml.c.id, snapshots.c.status == "ok")
        .order_by(snapshots.c.fetched_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    income_first = case((ml.c.income_monthly_usd > 0, 0), else_=1)
    rows = connection.execute(
        select(
            ml.c.id,
            ml.c.external_id,
            ml.c.title,
            ml.c.category,
            ml.c.subscribers,
            ml.c.price_usd,
            ml.c.income_monthly_usd,
            api_title.label("api_channel_title"),
        )
        .where(ml.c.source == source, ml.c.status == "active", ml.c.id.not_in(done))
        .order_by(
            income_first, ml.c.income_monthly_usd.desc().nulls_last(), ml.c.external_id.desc()
        )
        .limit(limit)
    ).mappings()
    return [dict(row) for row in rows]


def download_image(client: httpx.Client, url: str) -> Downloaded | None:
    """One attachment, in memory. Only the marketplace's media host, https, bounded size."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in IMAGE_HOSTS:
        return None
    try:
        with client.stream("GET", url, follow_redirects=False) as response:
            mime = response.headers.get("content-type", "").split(";")[0].strip().lower()
            if response.status_code != 200 or mime not in IMAGE_TYPES:
                return None
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > MAX_IMAGE_BYTES:
                    return None
    except httpx.HTTPError:
        return None
    return Downloaded(bytes(data), mime, hashlib.sha256(bytes(data)).hexdigest())


def save_evidence(
    connection: Connection,
    listing_id: UUID,
    *,
    state: str,
    now: datetime,
    total: int,
    hashes: list[str],
    reason: str | None = None,
    result: EvidenceResult | None = None,
    derived: dict[str, Any] | None = None,
) -> None:
    evidence = result.evidence if result else None
    connection.execute(
        le.insert().values(
            id=uuid4(),
            listing_id=listing_id,
            schema_version=SCHEMA_VERSION,
            prompt_version=PROMPT_VERSION,
            extraction_state=state,
            failure_reason=reason,
            extracted_at=now,
            image_count_total=total,
            image_count_processed=len(hashes),
            image_hashes=hashes,
            model_evidence=evidence.model_dump(mode="json") if evidence else None,
            derived=derived if derived else (result.diagnostic if result else None),
            evidence_grade=derived["evidence_grade"] if derived else None,
            income_level=derived["income_level"] if derived else None,
            observed_monthly_income_usd=(
                Decimal(derived["observed_monthly_income_usd"])
                if derived and derived["observed_monthly_income_usd"]
                else None
            ),
            rpm_usd=Decimal(derived["rpm_usd"]) if derived and derived["rpm_usd"] else None,
            rpm_sample_eligible=bool(derived and derived["rpm_sample_eligible"]),
            cost_usd=result.actual_usd if result else None,
            retain_until=now + LISTING_RETENTION,
        )
    )


async def extract(
    engine: Engine,
    run: dict[str, Any],
    config: Settings,
    listing: dict[str, Any],
    images: list[Downloaded],
    now: datetime,
    *,
    selector: OpenAISelector | None = None,
) -> dict[str, Any]:
    """One bounded vision call. Every decline carries a stable reason; nothing is persisted."""
    configuration, api_key = config.llm_configuration, config.llm_api_key
    if not config.llm_enabled:
        return {"result": None, "reason": "llm_disabled"}
    if run["mode"] != "live":
        return {"result": None, "reason": "synthetic_mode"}
    if configuration is None or api_key is None:
        return {"result": None, "reason": "configuration_missing"}
    tariff = configuration.tariff
    if not tariff.verified_at <= now < tariff.valid_until:
        return {"result": None, "reason": "llm_tariff_not_current"}
    key = cache_key(
        "openai",
        Operation.LISTING_EVIDENCE,
        {
            "listing_id": str(listing["id"]),
            "images": [image.sha256 for image in images],
            "prompt": PROMPT_VERSION,
        },
        configuration.auth_scope,
    )
    try:
        with engine.begin() as connection:
            for usage in (Usage.QUERY, Usage.STORAGE, Usage.DERIVED, Usage.LLM_PROCESSING):
                try:
                    require_usage(
                        connection,
                        "openai",
                        Operation.LISTING_EVIDENCE,
                        usage,
                        POLICY_DATA_TYPE,
                        now,
                    )
                except ProviderError:
                    return {"result": None, "reason": "policy_not_enabled"}
            request_id = prepare_request(
                connection,
                run["id"],
                "openai",
                Operation.LISTING_EVIDENCE,
                configuration.auth_scope,
                key,
                f"listing_evidence:{run['id']}:{listing['id']}",
                now,
            )
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
    except ProviderError as error:
        return {"result": None, "reason": error.code}
    context = {
        "untrusted_listing_title": listing.get("title"),
        "untrusted_category": listing.get("category"),
        "declared_subscribers": listing.get("subscribers"),
        "declared_income_monthly_usd": (
            str(listing["income_monthly_usd"]) if listing.get("income_monthly_usd") else None
        ),
        "api_channel_title": listing.get("api_channel_title"),
        "image_count": len(images),
    }
    body = request_body(tariff, context, [(image.data, image.mime) for image in images])
    try:
        client = selector or OpenAISelector(api_key)
        result: EvidenceResult = await client.select(
            body,
            configuration,
            parse_fn=parse_response,
            max_body_bytes=MAX_BODY_BYTES,
            timeout_seconds=VISION_TIMEOUT_SECONDS,
            max_response_bytes=400_000,
        )
    except Exception:
        with engine.begin() as connection:
            settle(connection, request_id, run["profile_id"], None, now)
        return {"result": None, "reason": "llm_failed"}
    with engine.begin() as connection:
        settle(
            connection,
            request_id,
            run["profile_id"],
            {"USD": result.actual_usd} if result.actual_usd is not None else None,
            now,
        )
    return {"result": result, "reason": result.reason}


def _stage(
    ctx: RunContext,
    pending: list[dict[str, Any]],
    http: httpx.Client,
    selector: OpenAISelector | None,
    sleep: Callable[[float], None],
) -> dict[str, Any]:
    counts = {"complete": 0, "no_images": 0, "failed": 0, "skipped": 0}
    stopped: str | None = None
    consecutive = 0
    cost = Decimal(0)
    for item in pending:
        now = ctx.clock()
        try:
            detail = ctx.source.fetch_detail(item["external_id"])
        except SourceError as error:
            if error.code != "source_unavailable":
                stopped = error.code
                break
            # One bad page degrades that listing only; a run of them means the source is down.
            consecutive += 1
            counts["skipped"] += 1
            if consecutive >= CONSECUTIVE_FAILURES_STOP:
                stopped = error.code
                break
            continue
        urls = tuple(detail.attachment_urls) if detail else ()
        if not urls:
            with ctx.engine.begin() as connection:
                reason = None if detail else "listing_gone"
                state = "no_images" if detail else "failed"
                save_evidence(
                    connection, item["id"], state=state, now=now, total=0, hashes=[], reason=reason
                )
            counts["no_images" if detail else "failed"] += 1
            continue
        images: list[Downloaded] = []
        seen: set[str] = set()
        for url in urls[:MAX_IMAGES]:
            sleep(1.0)
            found = download_image(http, url)
            if found is not None and found.sha256 not in seen:
                seen.add(found.sha256)
                images.append(found)
        hashes = [image.sha256 for image in images]
        if not images:
            with ctx.engine.begin() as connection:
                save_evidence(
                    connection,
                    item["id"],
                    state="failed",
                    now=now,
                    total=len(urls),
                    hashes=[],
                    reason="download_failed",
                )
            counts["failed"] += 1
            continue
        answer = asyncio.run(
            extract(ctx.engine, ctx.analysis_run, ctx.config, item, images, now, selector=selector)
        )
        result: EvidenceResult | None = answer["result"]
        if result is None:
            reason = answer["reason"]
            if reason in LISTING_LEVEL_DECLINES:
                counts["skipped"] += 1
                continue
            if reason == "llm_failed":
                consecutive += 1
                counts["skipped"] += 1
                if consecutive >= CONSECUTIVE_FAILURES_STOP:
                    stopped = reason
                    break
                continue
            stopped = reason
            break
        consecutive = 0
        cost += result.actual_usd or Decimal(0)
        if result.evidence is None:
            with ctx.engine.begin() as connection:
                save_evidence(
                    connection,
                    item["id"],
                    state="failed",
                    now=now,
                    total=len(urls),
                    hashes=hashes,
                    reason=result.reason,
                    result=result,
                )
            counts["failed"] += 1
            continue
        derived = build_derived(
            result.evidence, fx={}, extracted_at=now, declared_income=item["income_monthly_usd"]
        )
        with ctx.engine.begin() as connection:
            save_evidence(
                connection,
                item["id"],
                state="complete",
                now=now,
                total=len(urls),
                hashes=hashes,
                result=result,
                derived={**derived, "call": result.diagnostic},
            )
        counts["complete"] += 1
    outcome: dict[str, Any] = {"pending": len(pending), **counts, "cost_usd": str(cost)}
    if stopped is not None:
        outcome |= {"stopped_reason": stopped, "partial": True}
    return outcome


def stage_evidence(
    ctx: RunContext,
    *,
    http: httpx.Client | None = None,
    selector: OpenAISelector | None = None,
    sleep: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    config = ctx.config
    if ctx.analysis_run["mode"] != "live":
        return {"skipped": "synthetic_mode"}
    if config.market_intel_evidence_cap_per_run == 0 or not config.llm_enabled:
        return {"skipped": "evidence_not_enabled"}
    with ctx.engine.connect() as connection:
        pending = pending_evidence(
            connection, ctx.source.name, config.market_intel_evidence_cap_per_run, ctx.clock()
        )
    if not pending:
        return {"pending": 0}
    client = http or httpx.Client(
        headers={"User-Agent": "NicheRadar-MarketIntel/1.0 (+personal research)"},
        timeout=20,
        trust_env=False,
    )
    try:
        return _stage(ctx, pending, client, selector, sleep or time.sleep)
    finally:
        if http is None:
            client.close()
