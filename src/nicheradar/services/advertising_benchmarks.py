"""Lookup and construction of real, niche-tagged advertising benchmarks."""

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import Connection, select

from nicheradar.domain.production import EstimateRange
from nicheradar.domain.profile import VideoFormat
from nicheradar.repositories.schema import advertising_benchmarks
from nicheradar.scoring.advertising import AdUnit, AdvertisingBenchmark


def list_niche_options(connection: Connection) -> tuple[dict[str, str], ...]:
    rows = connection.execute(
        select(advertising_benchmarks.c.niche_label, advertising_benchmarks.c.niche_description)
    ).all()
    return tuple(
        {"niche_label": row.niche_label, "niche_description": row.niche_description} for row in rows
    )


def build_benchmark(
    connection: Connection, niche_label: str, now: datetime
) -> AdvertisingBenchmark | None:
    row = (
        connection.execute(
            select(advertising_benchmarks).where(
                advertising_benchmarks.c.niche_label == niche_label
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    video_format = VideoFormat(row["format"])
    unit: AdUnit = (
        "usd_ads_per_1000_engaged_views"
        if video_format == VideoFormat.SHORTS
        else "usd_ads_per_1000_views"
    )
    return AdvertisingBenchmark(
        version=f"{niche_label}-{row['created_at'].date().isoformat()}",
        source=row["source"],
        origin="manual_assumption",
        format=video_format,
        language="en",
        audience_key=niche_label,
        unit=unit,
        rate=EstimateRange(low=Decimal(str(row["rate_low"])), high=Decimal(str(row["rate_high"]))),
        revenue_scope="youtube_ads_only_after_revenue_share",
        assumptions=row["assumptions"],
        observed_at=now,
        valid_until=now + timedelta(days=180),
        usage="enabled",
        monetization="unknown",
    )
