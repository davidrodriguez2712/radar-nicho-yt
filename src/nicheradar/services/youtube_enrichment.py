"""Bounded YouTube metadata enrichment; discovery remains owned by vidIQ."""

from decimal import Decimal

from nicheradar.config import Settings
from nicheradar.integrations.contracts import Cost, Operation, ProviderError
from nicheradar.integrations.youtube import YouTubeProvider
from nicheradar.services.budget import Limits

YOUTUBE_TARIFF_SOURCE = "YouTube videos.list documentation verified 2026-09-23"


def youtube_provider(config: Settings) -> YouTubeProvider:
    if config.youtube_api_key is None:
        raise ProviderError("authentication_required", not_sent=True)
    if config.youtube_auth_scope is None:
        raise ProviderError("account_scope_required", not_sent=True)
    return YouTubeProvider(config.youtube_api_key, config.youtube_auth_scope, enabled=True)


def youtube_tariffs() -> dict[Operation, tuple[Cost, ...]]:
    return {
        Operation.VIDEOS: (
            Cost(unit="youtube_quota", maximum=Decimal(1), source=YOUTUBE_TARIFF_SOURCE),
        )
    }


def youtube_limits(config: Settings) -> dict[str, Limits]:
    return {
        "youtube_quota": Limits(
            operation=Decimal(1),
            run=Decimal(config.youtube_quota_per_run),
            week=Decimal(config.youtube_quota_per_week),
            period=Decimal(config.youtube_quota_per_month),
        )
    }
