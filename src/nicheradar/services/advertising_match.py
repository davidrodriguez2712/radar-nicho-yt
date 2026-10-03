"""One real, bounded LLM call per channel analysis: pick the best-matching real niche
RPM benchmark, or none. Mirrors services/explanations.py's reserve/settle pattern, but
synchronous within a single pipeline stage (channel-analysis stages already await
provider calls directly, unlike the catalog's post-commit explanation enrichment)."""

from datetime import datetime
from typing import Any

from sqlalchemy import Engine

from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile
from nicheradar.integrations.cache import cache_key
from nicheradar.integrations.contracts import Channel, Cost, Operation, ProviderError
from nicheradar.integrations.llm import (
    NicheMatchResult,
    OpenAISelector,
    niche_match_request_body,
    parse_niche_match_response,
)
from nicheradar.integrations.policies import Usage, require_usage
from nicheradar.services.advertising_benchmarks import list_niche_options
from nicheradar.services.budget import reserve, settle
from nicheradar.services.requests import mark_sent, prepare_request


async def match_niche(
    engine: Engine,
    run: dict[str, Any],
    profile: CreatorProfile,
    config: Settings,
    channel: Channel,
    now: datetime,
    *,
    selector: OpenAISelector | None = None,
) -> dict[str, Any]:
    """Pick a real seeded niche_label that best matches `channel`, or decline cleanly.

    `profile` is accepted for interface symmetry with the other channel-analysis stage
    helpers (and in case a future budget-confirmation gate needs it) but is not consulted
    directly: this call's own budget envelope is enforced entirely through
    `reserve()`/the provider policy checked below.
    """
    configuration = config.llm_configuration
    api_key = config.llm_api_key
    if not config.llm_enabled:
        return {"matched_niche": None, "reason": "llm_disabled"}
    # Mirrors explanations.py's enrich(): a synthetic (non-"live") channel-analysis run
    # must never place a real, billable provider call regardless of how `config.llm_*`
    # happens to be set in this environment.
    if run["mode"] != "live":
        return {"matched_niche": None, "reason": "synthetic_mode"}
    if configuration is None or api_key is None:
        return {"matched_niche": None, "reason": "configuration_missing"}
    tariff = configuration.tariff
    if not tariff.verified_at <= now < tariff.valid_until:
        return {"matched_niche": None, "reason": "llm_tariff_not_current"}
    with engine.begin() as connection:
        niches = list_niche_options(connection)
        if not niches:
            return {"matched_niche": None, "reason": "no_niches_configured"}
        for usage in (Usage.QUERY, Usage.STORAGE, Usage.DERIVED, Usage.LLM_PROCESSING):
            try:
                require_usage(
                    connection,
                    "openai",
                    Operation.NICHE_MATCH,
                    usage,
                    "channel_analysis_niche_match",
                    now,
                )
            except ProviderError:
                return {"matched_niche": None, "reason": "policy_not_enabled"}
        key = cache_key(
            "openai", Operation.NICHE_MATCH, {"channel_id": channel.id}, configuration.auth_scope
        )
        request_id = prepare_request(
            connection,
            run["id"],
            "openai",
            Operation.NICHE_MATCH,
            configuration.auth_scope,
            key,
            f"niche_match:{run['id']}",
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
    # The full catalog is ~218 real niches: embedding every real `niche_description`
    # verbatim (niche_match_request_body's "niche_options") pushes a realistic request
    # past OpenAISelector.select()'s fixed 32000-byte body cap on its own, before the
    # channel's own keywords/description are even added -- labels alone (already
    # readable snake_case phrases) stay comfortably within budget with room to spare
    # for the channel's side of the payload.
    prompt_niches = tuple({"niche_label": n["niche_label"]} for n in niches)
    body = niche_match_request_body(channel.keywords, channel.description, prompt_niches, tariff)
    valid_labels = tuple(n["niche_label"] for n in niches)
    try:
        client = selector or OpenAISelector(api_key)
        result: NicheMatchResult = await client.select(
            body,
            configuration,
            parse_fn=lambda payload, t: parse_niche_match_response(payload, t, valid_labels),
        )
    except Exception:
        with engine.begin() as connection:
            settle(connection, request_id, run["profile_id"], None, now)
        return {"matched_niche": None, "reason": "llm_failed"}
    with engine.begin() as connection:
        settle(
            connection,
            request_id,
            run["profile_id"],
            {"USD": result.actual_usd} if result.actual_usd is not None else None,
            now,
        )
    return {"matched_niche": result.niche_label, "reason": result.reason}
