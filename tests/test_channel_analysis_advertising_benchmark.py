from datetime import UTC, datetime, timedelta
from decimal import Decimal

from nicheradar.domain.production import EstimateRange
from nicheradar.domain.profile import CreatorProfile, VideoFormat
from nicheradar.scoring.advertising import AdvertisingBenchmark


def test_creator_profile_round_trips_an_optional_advertising_benchmark() -> None:
    now = datetime.now(UTC)
    benchmark = AdvertisingBenchmark(
        version="2026-10-02",
        source="owner_declared_estimate",
        origin="manual_assumption",
        format=VideoFormat.LONG,
        language="es",
        audience_key="general",
        unit="usd_ads_per_1000_views",
        rate=EstimateRange(low=Decimal("1.0"), high=Decimal("3.0")),
        revenue_scope="youtube_ads_only_after_revenue_share",
        assumptions="Estimación propia basada en benchmarks públicos del nicho.",
        observed_at=now,
        valid_until=now + timedelta(days=180),
    )
    profile = CreatorProfile(channel_analysis_advertising=benchmark.model_dump(mode="json"))
    restored = CreatorProfile.model_validate(profile.model_dump(mode="json"))
    assert restored.channel_analysis_advertising is not None
    # Stored raw — round-trip it back through AdvertisingBenchmark to prove it's valid.
    revalidated = AdvertisingBenchmark.model_validate(restored.channel_analysis_advertising)
    assert revalidated.rate.low == Decimal("1.0")


def test_creator_profile_defaults_advertising_benchmark_to_none() -> None:
    assert CreatorProfile().channel_analysis_advertising is None


def test_creator_profile_rejects_a_malformed_advertising_benchmark_dict() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AdvertisingBenchmark.model_validate({"not": "a real benchmark"})
