"""Deterministic invented fixtures, visibly distinct from live YouTube data."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from nicheradar.domain.profile import VideoFormat
from nicheradar.integrations.contracts import (
    Balance,
    Batch,
    Channel,
    Cost,
    Coverage,
    Metric,
    Operation,
    Provenance,
    ProviderError,
    Video,
)


class SyntheticProvider:
    name = "synthetic"
    operations = frozenset(Operation)

    def __init__(self) -> None:
        self.calls = 0

    async def fetch(self, operation: Operation, parameters: dict[str, Any], now: datetime) -> Batch:
        if operation not in self.operations:
            raise ProviderError("unsupported_operation")
        self.calls += 1
        family = str(parameters.get("family", "science"))
        common: dict[str, Any] = {
            "provenance": Provenance(
                provider=self.name,
                operation=operation,
                auth_scope="synthetic",
                fetched_at=now,
                observed_at=now,
                synthetic=True,
            ),
            "costs": (
                Cost(
                    unit="USD",
                    maximum=Decimal(0),
                    actual=Decimal(0),
                    source="invented fixture; no external request",
                ),
            ),
        }
        if operation == Operation.BALANCE:
            return Batch(
                **common,
                coverage=Coverage(returned=1, complete=True, selection_method="synthetic"),
                balance=Balance(
                    renewable=Decimal(150),
                    additional=Decimal(20),
                    recurring_allocation=Decimal(150),
                    renews_at=now + timedelta(days=30),
                ),
            )
        if operation == Operation.COMMENT_THREADS:
            return Batch(
                **common,
                comments=tuple(
                    {"text": f"Synthetic comment {index} about {family}", "like_count": index * 2}
                    for index in range(3)
                ),
                coverage=Coverage(returned=3, complete=True, selection_method="synthetic"),
            )
        if operation == Operation.VIDEO_CATEGORIES:
            return Batch(
                **common,
                category_labels={"24": "Entertainment", "27": "Education"},
                coverage=Coverage(returned=2, complete=True, selection_method="synthetic"),
            )
        if operation == Operation.SEARCH and parameters.get("type") == "video":
            operation = Operation.CHANNEL_VIDEOS  # falls through to the generic video fixture below
        if operation in {Operation.CHANNEL_SEARCH, Operation.CHANNELS, Operation.SEARCH}:
            channels = tuple(
                Channel(
                    id=f"synthetic:{family}:channel-{index}",
                    title=f"Synthetic {family} {index}",
                    subscribers=10_000 if index < 4 else 100_000,
                    country="US",
                    content_languages=("en",),
                    faceless=True,
                    category=family,
                    subtopics=(f"{family} explained",),
                    metrics={
                        "growth_percent": Metric(
                            value=None if index == 0 else 5,
                            unit="percent",
                            definition="synthetic percentage change",
                        ),
                        "growth_absolute": Metric(
                            value=0 if index == 0 else 500,
                            unit="subscribers",
                            definition="synthetic absolute change",
                        ),
                    },
                )
                for index in range(6)
            )
            return Batch(
                **common,
                channels=channels,
                coverage=Coverage(
                    returned=6,
                    reported_total=6,
                    complete=True,
                    selection_method="synthetic_stratified",
                ),
            )
        if operation == Operation.KEYWORDS:
            return Batch(
                **common,
                keywords=({"keyword": f"{family} explained", "volume": None},),
                coverage=Coverage(returned=1, complete=True, selection_method="synthetic"),
            )
        channel = str(parameters.get("channelId", f"synthetic:{family}:channel-0"))
        requested = str(parameters.get("videoFormat", "long"))
        formats = {
            "long": VideoFormat.LONG,
            "short": VideoFormat.SHORTS,
            "shorts": VideoFormat.SHORTS,
        }
        video_format = formats.get(requested, VideoFormat.UNKNOWN)
        videos = tuple(
            Video(
                id=f"{channel}:{requested}:video-{index}",
                channel_id=channel,
                title=f"Synthetic {family} explained {index}",
                published_at=now - timedelta(days=10),
                views=None if index == 7 else [0, 100, 100, 120, 130, 100, 1000][index],
                format=video_format if index != 7 else VideoFormat.UNKNOWN,
                format_evidence="synthetic fixture" if index != 7 else None,
                language="en" if index != 7 else None,
                language_evidence="synthetic fixture" if index != 7 else None,
                category=family,
                subscriber_count=10_000
                if "channel-4" not in channel and "channel-5" not in channel
                else 100_000,
                metrics={
                    "provider_breakout": Metric(
                        value=None, unit="provider_score", definition="not an own-baseline breakout"
                    )
                },
            )
            for index in range(8)
        )
        if operation == Operation.OUTLIERS:
            videos = (videos[6],)
        return Batch(
            **common,
            videos=videos,
            coverage=Coverage(
                returned=len(videos),
                complete=True,
                selection_method="outliers" if operation == Operation.OUTLIERS else "recent",
            ),
        )
