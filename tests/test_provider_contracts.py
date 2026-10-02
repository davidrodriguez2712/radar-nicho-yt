import asyncio
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from nicheradar.domain.profile import VideoFormat
from nicheradar.integrations.cache import cache_key
from nicheradar.integrations.contracts import Cost, Metric, Operation
from nicheradar.integrations.synthetic import SyntheticProvider

NOW = datetime(2026, 9, 13, tzinfo=UTC)


def test_synthetic_null_zero_units_and_unknown() -> None:
    provider = SyntheticProvider()
    batch = asyncio.run(provider.fetch(Operation.CHANNEL_VIDEOS, {}, NOW))
    assert batch.provenance.synthetic
    assert batch.videos[0].views == 0
    assert batch.videos[-1].views is None
    assert batch.videos[-1].format == VideoFormat.UNKNOWN
    assert batch.videos[0].metrics["provider_breakout"].value is None
    assert batch.costs[0].actual == 0
    channels = asyncio.run(provider.fetch(Operation.CHANNEL_SEARCH, {}, NOW)).channels
    assert channels[0].metrics["growth_percent"].unit != channels[0].metrics["growth_absolute"].unit
    assert channels[0].country == "US"
    assert channels[0].audience_countries == ()


def test_invalid_numbers_rejected() -> None:
    with pytest.raises(ValidationError):
        Metric(value=float("nan"), unit="percent", definition="invalid")
    with pytest.raises(ValidationError):
        Cost.model_validate({"unit": "USD", "maximum": -1, "source": "invalid"})
    assert Cost(unit="USD", source="unknown").maximum is None


def test_canonical_cache_is_scoped_and_versioned() -> None:
    def key(parameters: dict[str, object], account: str = "account-a", version: str = "v1") -> str:
        return cache_key("synthetic", Operation.CHANNEL_SEARCH, parameters, account, version)

    assert key({"query": "space", "languages": ["en"]}) == key(
        {"languages": ["en"], "query": "space"}
    )
    assert key({"query": "space"}) != key({"query": "space"}, "account-b")
    assert key({"query": "space"}) != key({"query": "space"}, version="v2")
    assert key({"query": "space"}) != key({"query": "space", "language": "en"})
