from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import Connection

from nicheradar.domain.profile import VideoFormat
from nicheradar.scoring.advertising import AdvertisingBenchmark
from nicheradar.services.advertising_benchmarks import build_benchmark, list_niche_options


def test_list_niche_options_returns_all_rows(db: Connection) -> None:
    options = list_niche_options(db)
    assert len(options) == 218
    assert {"niche_label", "niche_description"} <= options[0].keys()


def test_build_benchmark_for_known_label(db: Connection) -> None:
    now = datetime(2026, 10, 3, tzinfo=UTC)
    benchmark = build_benchmark(db, "true_crime_stories", now)
    assert benchmark is not None
    assert benchmark.format == VideoFormat.LONG
    assert benchmark.unit == "usd_ads_per_1000_views"
    assert benchmark.rate.low <= benchmark.rate.high
    assert benchmark.observed_at == now
    assert benchmark.valid_until > now


def test_build_benchmark_for_unknown_label(db: Connection) -> None:
    assert build_benchmark(db, "no_existe", datetime.now(UTC)) is None


def test_advertising_benchmark_rejects_a_malformed_dict() -> None:
    with pytest.raises(ValidationError):
        AdvertisingBenchmark.model_validate({"not": "a real benchmark"})
