# tests/test_subniche_aggregate.py
from decimal import Decimal

from nicheradar.subniche_discovery.aggregate import HitMetrics, build_profile, is_stable


def hit(
    letter: str = "a",
    *,
    low: str | None = "100",
    high: str | None = "200",
    subs: int | None = 5_000,
    traction: bool = False,
    flags: tuple[str, ...] = (),
    excluded: str | None = None,
    ratio: str | None = "1.00",
) -> HitMetrics:
    return HitMetrics(
        channel_id="UC" + letter * 22,
        source="search",
        rank=1,
        subscribers=subs,
        monthly_long_views=10_000,
        income_low=Decimal(low) if low else None,
        income_high=Decimal(high) if high else None,
        shorts_share=None,
        outlier_ratio_max=Decimal(ratio) if ratio else None,
        small_channel=subs is not None and subs < 100_000,
        traction=traction,
        flags=flags,
        excluded_reason=excluded,
    )


def test_volatile_and_excluded_channels_do_not_enter_the_median() -> None:
    hits = [
        hit("a", low="100", high="200"),
        hit("b", low="300", high="500"),
        hit("c", low="9000", high="9999", flags=("young",)),
        hit("d", low="8000", high="8999", excluded="language"),
    ]
    profile = build_profile(hits, rpm_source="inherited:historical_stories")
    assert profile["stable_channels"] == 2
    assert profile["volatile_channels"] == 1
    assert profile["excluded"] == {"language": 1}
    assert profile["median_income_low"] == "200.00"
    assert profile["median_income_high"] == "350.00"
    assert profile["estimate"] is True
    assert profile["rpm_source"] == "inherited:historical_stories"


def test_traction_and_competition_are_counted_over_included_channels() -> None:
    hits = [
        hit("a", traction=True, ratio="12.00"),
        hit("b", traction=True, ratio="6.00"),
        hit("c", subs=250_000),
        hit("d", excluded="language", traction=True),
    ]
    profile = build_profile(hits, rpm_source=None)
    assert profile["traction_channels"] == 2
    assert profile["median_outlier_ratio"] == "9.00"
    assert profile["large_channels"] == 1


def test_no_rpm_means_no_income_but_still_a_profile() -> None:
    profile = build_profile([hit(low=None, high=None)], rpm_source=None)
    assert profile["median_income_low"] is None and profile["median_income_high"] is None
    assert profile["signal"] == "estimable"


def test_empty_or_fully_excluded_is_sin_senal() -> None:
    assert build_profile([], rpm_source=None)["signal"] == "sin_senal"
    only_excluded = build_profile([hit(excluded="language")], rpm_source=None)
    assert only_excluded["signal"] == "sin_senal" and only_excluded["channels_seen"] == 1


def test_is_stable_requires_no_volatile_flag_and_no_exclusion() -> None:
    assert is_stable(hit()) is True
    assert is_stable(hit(flags=("spike",))) is False
    assert is_stable(hit(excluded="language")) is False
