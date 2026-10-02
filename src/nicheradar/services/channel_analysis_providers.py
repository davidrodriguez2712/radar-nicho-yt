"""Tariffs and limits for the channel-analysis flow only; separate from the
scheduled-cycle YouTube enrichment budget (src/nicheradar/services/youtube_enrichment.py)
and the pilot vidIQ budget (src/nicheradar/services/pilot.py) — this feature needs its
own higher per-run vidIQ cap (Task 6) and its own YouTube search-vs-detail split
(search.list has its own 100/day bucket; detail calls share the general 10,000/day pool).
"""

from decimal import Decimal

from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile
from nicheradar.integrations.contracts import Cost, Operation
from nicheradar.services.budget import Limits

YOUTUBE_TARIFF_SOURCE = (
    "YouTube Data API v3 docs, search.list/commentThreads.list/"
    "videoCategories.list verified 2026-10-01"
)
VIDIQ_TARIFF_SOURCE = "MCP tools/list reviewed 2026-09-21; flat 5 credits per call"


def channel_analysis_youtube_tariffs() -> dict[Operation, tuple[Cost, ...]]:
    detail_cost = Cost(
        unit="youtube_detail_quota", maximum=Decimal(1), source=YOUTUBE_TARIFF_SOURCE
    )
    return {
        Operation.CHANNELS: (detail_cost,),
        Operation.UPLOADS: (detail_cost,),
        Operation.VIDEOS: (detail_cost,),
        Operation.COMMENT_THREADS: (detail_cost,),
        Operation.VIDEO_CATEGORIES: (detail_cost,),
        Operation.SEARCH: (
            Cost(unit="youtube_search_quota", maximum=Decimal(100), source=YOUTUBE_TARIFF_SOURCE),
        ),
    }


def channel_analysis_youtube_limits(config: Settings) -> dict[str, Limits]:
    return {
        "youtube_search_quota": Limits(
            operation=Decimal(100),
            run=Decimal(config.youtube_search_quota_per_run),
            week=Decimal(config.youtube_search_quota_per_week),
            period=Decimal(config.youtube_search_quota_per_month),
        ),
        "youtube_detail_quota": Limits(
            operation=Decimal(1),
            run=Decimal(config.youtube_detail_quota_per_run),
            week=Decimal(config.youtube_detail_quota_per_week),
            period=Decimal(config.youtube_detail_quota_per_month),
        ),
    }


def channel_analysis_vidiq_tariffs() -> dict[Operation, tuple[Cost, ...]]:
    cost = Cost(unit="vidiq_credit", maximum=Decimal(5), source=VIDIQ_TARIFF_SOURCE)
    return {
        Operation.CHANNEL_SEARCH: (cost,),
        Operation.CHANNEL_VIDEOS: (cost,),
        Operation.OUTLIERS: (cost,),
        Operation.KEYWORDS: (cost,),
        # Gateway.fetch() requires a verified free (maximum=0) BALANCE tariff before it
        # will refresh the balance automatically (see services/pilot.py::vidiq_tariffs);
        # without this entry every live call degrades with "balance_refresh_required".
        Operation.BALANCE: (
            Cost(unit="vidiq_credit", maximum=Decimal(0), source=VIDIQ_TARIFF_SOURCE),
        ),
    }


def channel_analysis_vidiq_limits(profile: CreatorProfile) -> dict[str, Limits]:
    return {
        "vidiq_credit": Limits(
            operation=Decimal(5),
            run=Decimal(profile.channel_analysis_credits_per_run),
            week=Decimal(profile.credits_per_week),
            period=Decimal(profile.credits_per_cycle),
        )
    }
