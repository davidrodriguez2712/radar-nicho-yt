"""`subniche add`: input -> source text -> LLM proposal (or manual fields) -> `proposed` row."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, NoReturn

from pydantic import ValidationError
from sqlalchemy import Engine

from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.integrations.anthropic import AnthropicClient
from nicheradar.integrations.contracts import Channel, ProviderError, Video
from nicheradar.market_intel.classify import niche_labels
from nicheradar.market_intel.context import utcnow
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.subniche_discovery.contracts import HypothesisDraft, slugify
from nicheradar.subniche_discovery.inputs import parse_input, resolve_source
from nicheradar.subniche_discovery.propose import propose_hypothesis
from nicheradar.subniche_discovery.reader import YouTubeReader, build_reader
from nicheradar.subniche_discovery.store import (
    DuplicateHypothesis,
    create_proposed,
    unique_slug,
)

MIN_SLUG_LENGTH = 3


@dataclass(frozen=True)
class ManualFields:
    label: str
    family: str
    parent: str | None


class _NoReader:
    """A query needs no YouTube call; any attempt to use the reader is a bug."""

    @staticmethod
    def _never() -> NoReturn:
        raise AssertionError("a query source never reads YouTube")

    async def search(
        self, query: str, published_after: datetime, page_token: str | None
    ) -> tuple[list[Video], str | None]:
        self._never()

    async def channels(self, ids: list[str]) -> dict[str, Channel]:
        self._never()

    async def channel_by_handle(self, handle: str) -> Channel | None:
        self._never()

    async def recent_videos(self, channel: Channel, limit: int) -> tuple[Video, ...]:
        self._never()

    async def video(self, video_id: str) -> Video | None:
        self._never()


def _proposal_run(engine: Engine, config: Settings) -> dict[str, Any]:
    with engine.begin() as connection:
        profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
        run_id = insert_record(
            connection,
            "analysis_runs",
            {
                "profile_id": profile_id,
                "mode": config.mode,
                "trigger": "subniche_propose",
                "status": "queued",
                "configuration": {},
            },
        )
    return {"id": run_id, "profile_id": profile_id, "mode": config.mode}


async def add_hypothesis(
    engine: Engine,
    config: Settings,
    raw: str,
    *,
    origin: str = "manual",
    manual: ManualFields | None = None,
    reader: YouTubeReader | None = None,
    client: AnthropicClient | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> dict[str, Any]:
    now = clock()
    try:
        parsed = parse_input(raw)
    except ValueError as error:
        return {"error": "invalid_input", "detail": str(error)}
    if parsed.kind == "tweet":
        return {"error": "tweet_not_supported_yet"}
    run = _proposal_run(engine, config)
    source: dict[str, Any]
    if parsed.kind == "query":
        source = await resolve_source(parsed, _NoReader())
    else:
        try:
            active = reader or build_reader(engine, config, run, clock)
            source = await resolve_source(parsed, active)
        except ProviderError as error:
            return {"error": error.code}
        except LookupError as error:
            return {"error": "not_found", "detail": str(error)}
    with engine.connect() as connection:
        labels = niche_labels(connection)
    llm_usd: str | None = None
    if manual is not None:
        if manual.parent is not None and manual.parent not in labels:
            return {"error": "unknown_parent_niche"}
        label, family, parent = manual.label, manual.family, manual.parent
        queries: tuple[str, ...] = (parsed.value,) if parsed.kind == "query" else ()
        if not queries:
            return {"error": "manual_needs_a_query", "detail": "pass a query with --manual"}
    else:
        outcome = await propose_hypothesis(engine, run, config, source, labels, now, client=client)
        result = outcome["proposal"]
        if result is None or result.proposal is None:
            return {"error": outcome["reason"], "hint": "use --manual to add without the LLM"}
        proposal = result.proposal
        label, family, parent, queries = (
            proposal.label,
            proposal.family,
            proposal.parent_niche,
            proposal.queries,
        )
        llm_usd = str(result.actual_usd) if result.actual_usd is not None else None
    label = " ".join(label.split())
    if len(slugify(label)) < MIN_SLUG_LENGTH:
        return {"error": "invalid_proposal", "detail": "label has no usable text"}
    seeds = (source["channel_id"],) if source.get("channel_id") else ()
    try:
        with engine.begin() as connection:
            draft = HypothesisDraft(
                slug=unique_slug(connection, slugify(label)),
                label=label,
                family=family,
                parent_niche_slug=parent,
                queries=queries,
                origin=origin,
                source_input=raw.strip()[:500],
                seed_channel_ids=seeds,
            )
            create_proposed(connection, draft, now)
    except DuplicateHypothesis as error:
        return {"error": f"duplicate:{error.reason}"}
    except ValidationError as error:
        return {"error": "invalid_proposal", "detail": str(error.errors()[0]["msg"])}
    return {
        "status": "proposed",
        "slug": draft.slug,
        "label": draft.label,
        "family": draft.family,
        "parent_niche": draft.parent_niche_slug,
        "queries": list(draft.queries),
        "seed_channels": list(draft.seed_channel_ids),
        "llm_usd": llm_usd,
        "next": f"subniche approve {draft.slug}",
    }
