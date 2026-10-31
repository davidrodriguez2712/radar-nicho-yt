# src/nicheradar/subniche_discovery/persist.py
"""Storage of one hypothesis measurement: all of it or none of it (one transaction)."""

from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, select

from nicheradar.integrations.contracts import Channel, Video
from nicheradar.repositories.schema import advertising_benchmarks
from nicheradar.repositories.schema import discovery_channel_snapshots as snapshots
from nicheradar.repositories.schema import hypothesis_channel_hits as hits_table
from nicheradar.repositories.schema import hypothesis_snapshots as profiles
from nicheradar.subniche_discovery.aggregate import HitMetrics
from nicheradar.subniche_discovery.store import mark_measured

API_RETENTION = timedelta(days=30)
RECENT_VIDEOS_KEPT = 30


def rpm_range(
    connection: Connection, niche_label: str | None
) -> tuple[Decimal, Decimal, str] | None:
    if niche_label is None:
        return None
    row = connection.execute(
        select(advertising_benchmarks.c.rate_low, advertising_benchmarks.c.rate_high).where(
            advertising_benchmarks.c.niche_label == niche_label,
            advertising_benchmarks.c.format == "long",
        )
    ).first()
    if row is None:
        return None
    return Decimal(str(row.rate_low)), Decimal(str(row.rate_high)), f"inherited:{niche_label}"


def save_measurement(
    connection: Connection,
    *,
    hypothesis_id: UUID,
    run_id: UUID,
    now: datetime,
    channels: Sequence[tuple[Channel, Sequence[Video]]],
    hits: Sequence[HitMetrics],
    profile: dict[str, Any],
) -> None:
    retain_until = now + API_RETENTION
    for channel, videos in channels:
        ordered = sorted(
            videos,
            key=lambda v: v.published_at or datetime.min.replace(tzinfo=now.tzinfo),
            reverse=True,
        )
        connection.execute(
            snapshots.insert().values(
                id=uuid4(),
                run_id=run_id,
                channel_id=channel.id,
                fetched_at=now,
                title=channel.title[:200],
                country=channel.country,
                channel_created_at=channel.published_at,
                subscribers=channel.subscribers,
                total_views=channel.total_views,
                video_count=channel.video_count,
                recent_videos=[
                    {
                        "video_id": video.id,
                        "title": video.title[:120],
                        "published_at": video.published_at.isoformat()
                        if video.published_at
                        else None,
                        "duration_seconds": int(video.duration_seconds)
                        if video.duration_seconds is not None
                        else None,
                        "views": video.views,
                    }
                    for video in ordered[:RECENT_VIDEOS_KEPT]
                ],
                retain_until=retain_until,
            )
        )
    for hit in hits:
        connection.execute(
            hits_table.insert().values(
                id=uuid4(),
                hypothesis_id=hypothesis_id,
                run_id=run_id,
                channel_id=hit.channel_id,
                source=hit.source,
                rank=hit.rank,
                subscribers=hit.subscribers,
                monthly_long_views=hit.monthly_long_views,
                income_low=hit.income_low,
                income_high=hit.income_high,
                shorts_share=hit.shorts_share,
                outlier_ratio_max=hit.outlier_ratio_max,
                small_channel=hit.small_channel,
                traction=hit.traction,
                flags=list(hit.flags),
                excluded_reason=hit.excluded_reason,
                retain_until=retain_until,
            )
        )
    connection.execute(
        profiles.insert().values(
            id=uuid4(),
            hypothesis_id=hypothesis_id,
            run_id=run_id,
            measured_at=now,
            stable_channels=profile["stable_channels"],
            traction_channels=profile["traction_channels"],
            median_income_low=Decimal(profile["median_income_low"])
            if profile["median_income_low"]
            else None,
            median_income_high=Decimal(profile["median_income_high"])
            if profile["median_income_high"]
            else None,
            profile=profile,
        )
    )
    mark_measured(connection, hypothesis_id, now)
