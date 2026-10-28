"""listing-evidence-v1: validaciones (V1-V12), conjuntos, grados y recalibración de RPM."""

from copy import deepcopy
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from nicheradar.market_intel.evidence.contracts import ApiEvidence, ModelEvidence, RecentVideo
from nicheradar.market_intel.evidence.derive import (
    code_risk_flags,
    grade,
    monthly_views_lower_bound,
    observation_sets,
    rpm_sample_eligible,
    select_primary,
)
from nicheradar.market_intel.evidence.reconcile import (
    drop_unverifiable_entries,
    parse_raw_number,
    raw_text_matches,
)
from nicheradar.market_intel.evidence.rpm import RpmSample, recalibrate

NOW = datetime(2026, 10, 28, 12, tzinfo=UTC)
TODAY = NOW.date()


def period(kind: str, start: str, end: str) -> dict[str, Any]:
    return {"kind": kind, "start": start, "end": end}


def base(**over: Any) -> dict[str, Any]:
    """Un canal con YPP activo y una captura reciente de 28 días (grado A por construcción)."""
    window = period("last_28d", "2026-09-29", "2026-10-26")
    doc: dict[str, Any] = {
        "images": [
            {
                "index": 0,
                "kind": "studio_revenue",
                "captured_on": "2026-10-26",
                "captured_on_basis": "visible_in_image",
                "currency_visible": "USD",
            }
        ],
        "identity_check": {"matches_listing_title": "yes", "matches_api_channel": "yes"},
        "monetization": {
            "ypp_status": "active",
            "payments_status": "configured",
            "monetized_since": "2025-01-01",
            "monetized_since_basis": "visible_in_image",
            "evidence_images": [0],
        },
        "earnings": [
            {
                "image_index": 0,
                "scope": "all",
                "metric": "estimated_revenue",
                "period": window,
                "amount": {"value": "295.18", "currency": "USD"},
                "raw_text": "$295.18",
                "legibility": "clear",
            }
        ],
        "views": [
            {
                "image_index": 0,
                "scope": "all",
                "metric": "views",
                "period": window,
                "value": 69700,
                "raw_text": "69.7K",
                "legibility": "clear",
            }
        ],
    }
    return doc | over


def parse(doc: dict[str, Any]) -> ModelEvidence:
    return ModelEvidence.model_validate(doc)


def evaluate(
    doc: dict[str, Any], fx: dict[tuple[str, date], Decimal] | None = None, *, api: bool = False
) -> str:
    evidence = parse(doc)
    sets = observation_sets(evidence, fx or {}, TODAY)
    primary = select_primary(sets)
    return grade(evidence, primary, sets, has_api_views=api)


# --- V1-V10: el contrato rechaza lo que no cumple --------------------------------------------


@pytest.mark.parametrize("forbidden", ["derived", "api", "meta", "declared", "surprise"])
def test_the_model_cannot_send_code_owned_or_unknown_blocks(forbidden: str) -> None:
    with pytest.raises(ValidationError):
        parse(base(**{forbidden: {}}))


def test_an_image_reference_must_exist() -> None:
    doc = base()
    doc["earnings"][0]["image_index"] = 7
    with pytest.raises(ValidationError, match="unknown_image_index"):
        parse(doc)


def test_a_period_must_be_ordered_and_dated() -> None:
    doc = base()
    doc["earnings"][0]["period"] = period("last_28d", "2026-10-26", "2026-09-29")
    with pytest.raises(ValidationError, match="period_start_after_end"):
        parse(doc)
    doc["earnings"][0]["period"] = {"kind": "last_28d", "start": "2026-09-29"}
    with pytest.raises(ValidationError, match="period_dates_required"):
        parse(doc)


def test_lifetime_may_omit_its_dates() -> None:
    doc = base()
    doc["earnings"][0]["period"] = {"kind": "lifetime"}
    assert parse(doc).earnings[0].period.days is None


def test_money_needs_a_currency_and_cannot_be_negative() -> None:
    doc = base()
    del doc["earnings"][0]["amount"]["currency"]
    with pytest.raises(ValidationError):
        parse(doc)
    doc = base()
    doc["earnings"][0]["amount"]["value"] = "-1"
    with pytest.raises(ValidationError):
        parse(doc)


def test_every_number_carries_its_literal_text() -> None:
    doc = base()
    del doc["views"][0]["raw_text"]
    with pytest.raises(ValidationError):
        parse(doc)


def test_only_net_subscribers_may_be_negative() -> None:
    doc = base()
    doc["views"][0]["value"] = -5
    with pytest.raises(ValidationError, match="negative_metric"):
        parse(doc)
    doc["views"][0]["metric"] = "subscribers_net"
    parse(doc)


def test_country_shares_cannot_exceed_one_hundred() -> None:
    doc = base(
        audience={
            "scope": "channel",
            "countries": [{"code": "US", "pct": 70}, {"code": "IN", "pct": 40}],
            "image_index": 0,
        }
    )
    with pytest.raises(ValidationError, match="country_shares_exceed_100"):
        parse(doc)


def test_the_model_cannot_emit_flags_the_code_computes() -> None:
    flag = {"code": "stale_capture", "severity": "low", "origin": "model"}
    with pytest.raises(ValidationError):
        parse(base(risk_flags=[flag]))
    code_origin = {"code": "copyright_risk", "severity": "low", "origin": "code"}
    with pytest.raises(ValidationError):
        parse(base(risk_flags=[code_origin]))
    ok = {"code": "copyright_risk", "severity": "low", "origin": "model", "evidence": [0]}
    assert parse(base(risk_flags=[ok])).risk_flags[0].code == "copyright_risk"


def test_at_most_twelve_images() -> None:
    images = [{"index": i, "kind": "unrelated", "captured_on_basis": "unknown"} for i in range(13)]
    with pytest.raises(ValidationError):
        parse(base(images=images))


# --- V12: el texto literal debe reproducir el número ------------------------------------------


@pytest.mark.parametrize(
    ("raw", "value"),
    [
        ("$295.18", 295.18),
        ("69.7K", 69700),
        ("1.0K", 1000),
        ("1,276.14", 1276.14),
        ("1.276,14", 1276.14),
        ("US$ 4,320.47", 4320.47),
        ("£0.04", 0.04),
        ("12.2M", 12_200_000),
        ("51,507", 51507),
        ("-273", -273),
    ],
)
def test_raw_text_reproduces_the_value(raw: str, value: float) -> None:
    assert raw_text_matches(raw, value)


@pytest.mark.parametrize(
    ("raw", "value"), [("69.7K", 97000), ("$295.18", 259.18), ("sin cifra", 10), ("1,276", 1.276)]
)
def test_raw_text_that_does_not_match_is_rejected(raw: str, value: float) -> None:
    assert not raw_text_matches(raw, value)


def test_thousands_with_three_digits_are_not_decimals() -> None:
    assert parse_raw_number("1,276")[0] == Decimal(1276)  # type: ignore[index]


def test_a_misread_entry_moves_to_unresolved_and_the_rest_survives() -> None:
    doc = base()
    doc["views"][0]["raw_text"] = "97.6K"  # no coincide con 69700
    cleaned = drop_unverifiable_entries(parse(doc))
    assert cleaned.views == () and len(cleaned.earnings) == 1
    assert cleaned.unresolved[-1].topic == "views" and cleaned.unresolved[-1].reason == "unreadable"


def test_nothing_changes_when_every_entry_verifies() -> None:
    evidence = parse(base())
    assert drop_unverifiable_entries(evidence) is evidence


# --- conjuntos de observación y RPM calculado --------------------------------------------------


def test_the_same_period_pairs_revenue_with_views_and_computes_the_rpm() -> None:
    sets = observation_sets(parse(base()), {}, TODAY)
    assert len(sets) == 1
    found = sets[0]
    assert round(found.rpm_usd, 3) == Decimal("4.235")
    assert round(found.monthly_revenue_usd, 1) == Decimal("320.9")  # type: ignore[arg-type]
    assert found.capture_age_days == 2


def test_different_periods_or_scopes_never_pair() -> None:
    doc = base()
    doc["views"][0]["period"] = period("last_90d", "2026-07-29", "2026-10-26")
    assert observation_sets(parse(doc), {}, TODAY) == ()
    doc = base()
    doc["views"][0]["scope"] = "shorts"
    assert observation_sets(parse(doc), {}, TODAY) == ()


def test_periods_one_day_apart_with_the_same_kind_still_pair() -> None:
    doc = base()
    doc["views"][0]["period"] = period("last_28d", "2026-09-30", "2026-10-27")
    assert len(observation_sets(parse(doc), {}, TODAY)) == 1


def test_foreign_currency_needs_a_dated_rate_or_it_is_skipped() -> None:
    doc = base()
    doc["earnings"][0]["amount"] = {"value": "362.55", "currency": "EUR"}
    doc["earnings"][0]["raw_text"] = "EUR 362.55"
    assert observation_sets(parse(doc), {}, TODAY) == ()
    fx = {("EUR", date(2026, 10, 26)): Decimal("1.08")}
    found = observation_sets(parse(doc), fx, TODAY)[0]
    assert round(found.revenue_usd, 2) == Decimal("391.55") and found.currency == "EUR"


def test_the_primary_set_prefers_28_days_ignores_lifetime_and_shorts() -> None:
    doc = base()
    window90 = period("last_90d", "2026-07-29", "2026-10-26")
    life = {"kind": "lifetime"}
    doc["earnings"] += [
        {
            **doc["earnings"][0],
            "period": window90,
            "amount": {"value": "900", "currency": "USD"},
            "raw_text": "$900",
        },
        {
            **doc["earnings"][0],
            "period": life,
            "amount": {"value": "9000", "currency": "USD"},
            "raw_text": "$9,000",
        },
        {
            **doc["earnings"][0],
            "scope": "shorts",
            "amount": {"value": "5", "currency": "USD"},
            "raw_text": "$5",
        },
    ]
    doc["views"] += [
        {**doc["views"][0], "period": window90, "value": 200000, "raw_text": "200K"},
        {**doc["views"][0], "period": life, "value": 5000000, "raw_text": "5M"},
        {**doc["views"][0], "scope": "shorts", "value": 90000, "raw_text": "90K"},
    ]
    sets = observation_sets(parse(doc), {}, TODAY)
    assert len(sets) == 4
    primary = select_primary(sets)
    assert primary is not None and primary.period.kind == "last_28d" and primary.scope == "all"
    assert select_primary(tuple(s for s in sets if s.period.kind == "lifetime")) is None


# --- grados -------------------------------------------------------------------------------------


def test_a_fresh_confirmed_monetized_channel_is_grade_a() -> None:
    assert evaluate(base()) == "A"


def test_one_relaxed_condition_is_grade_b_and_two_are_grade_c() -> None:
    doc = base()
    doc["images"][0]["captured_on"] = "2026-06-01"  # 149 días
    assert evaluate(doc) == "B"
    doc["views"][0]["value"] = 5000
    doc["views"][0]["raw_text"] = "5.0K"
    assert evaluate(doc) == "C"


def test_a_capture_older_than_a_year_is_grade_c() -> None:
    doc = base()
    doc["images"][0]["captured_on"] = "2024-07-18"
    assert evaluate(doc) == "C"


def test_identity_that_cannot_be_told_caps_the_grade_at_c() -> None:
    doc = base()
    doc["identity_check"]["matches_api_channel"] = "cannot_tell"
    assert evaluate(doc) == "C"


def test_a_different_channel_is_excluded_entirely() -> None:
    doc = base()
    doc["identity_check"]["matches_api_channel"] = "no"
    assert evaluate(doc) == "X"
    doc = base()
    doc["identity_check"] = {"matches_listing_title": "no", "matches_api_channel": "cannot_tell"}
    assert evaluate(doc) == "X"


def test_revenue_without_matching_views_is_grade_c() -> None:
    doc = base()
    doc["views"] = []
    assert evaluate(doc) == "C"


def test_no_revenue_but_api_views_is_grade_d_and_nothing_is_grade_e() -> None:
    doc = base(earnings=[], views=[])
    assert evaluate(doc, api=True) == "D"
    assert evaluate(doc, api=False) == "E"


@pytest.mark.parametrize("status", ["suspended", "not_eligible", "base_terms_only"])
def test_a_channel_that_is_not_monetized_is_grade_e(status: str) -> None:
    doc = base()
    doc["monetization"]["ypp_status"] = status
    assert evaluate(doc) == "E"


def test_high_severity_inconsistency_excludes_the_listing() -> None:
    evidence = parse(base())
    sets = observation_sets(evidence, {}, TODAY)
    result = grade(
        evidence, select_primary(sets), sets, has_api_views=False, high_severity_inconsistency=True
    )
    assert result == "X"


# --- elegibilidad para la muestra de RPM -----------------------------------------------------


def eligible(doc: dict[str, Any]) -> bool:
    evidence = parse(doc)
    sets = observation_sets(evidence, {}, TODAY)
    primary = select_primary(sets)
    return rpm_sample_eligible(
        primary, evidence, grade(evidence, primary, sets, has_api_views=False)
    )


def test_a_clean_28_day_long_form_set_feeds_the_rpm_sample() -> None:
    assert eligible(base())


def test_short_periods_small_samples_and_recent_monetization_do_not() -> None:
    doc = base()
    doc["earnings"][0]["period"] = period("last_7d", "2026-10-20", "2026-10-26")
    doc["views"][0]["period"] = period("last_7d", "2026-10-20", "2026-10-26")
    assert not eligible(doc)
    doc = base()
    doc["views"][0].update(value=9000, raw_text="9.0K")
    assert not eligible(doc)
    doc = base()
    doc["monetization"]["monetized_since"] = "2026-10-01"  # empezó dentro del periodo
    assert not eligible(doc)


def test_unconfirmed_identity_never_feeds_the_rpm_sample() -> None:
    doc = base()
    doc["identity_check"]["matches_api_channel"] = "cannot_tell"
    assert not eligible(doc)


# --- recalibración -----------------------------------------------------------------------------


def sample(
    listing: str, rpm: float, views: float = 100_000, age: int = 30, grade_: str = "A"
) -> RpmSample:
    return RpmSample(listing, rpm, views, age, grade_)  # type: ignore[arg-type]


def test_fewer_than_three_samples_keep_the_catalog_midpoint() -> None:
    estimate = recalibrate([sample("1", 0.3), sample("2", 1.4)], 4.0, 12.0)
    assert (estimate.state, estimate.rpm_usd, estimate.n) == ("catalog", 8.0, 2)


def test_three_or_four_samples_blend_with_the_prior_and_flag_the_range() -> None:
    samples = [sample("1", 0.3), sample("2", 1.4), sample("3", 0.2)]
    estimate = recalibrate(samples, 4.0, 12.0)
    assert estimate.state == "blended" and estimate.n == 3
    assert 0.3 < estimate.rpm_usd < 8.0
    assert estimate.out_of_catalog_range  # la mediana observada queda bajo el rango del catálogo
    assert round(estimate.rpm_usd, 2) == round((3 * 0.3 + 5 * 8.0) / 8, 2)


def test_five_samples_use_the_weighted_median() -> None:
    samples = [sample(str(i), r) for i, r in enumerate([3.9, 4.1, 4.2, 4.6, 1.8])]
    estimate = recalibrate(samples, 3.5, 8.0)
    assert estimate.state == "observed" and estimate.rpm_usd == 4.1
    assert not estimate.out_of_catalog_range
    assert estimate.p25 is not None and estimate.p75 is not None
    assert estimate.p25 <= estimate.rpm_usd <= estimate.p75


def test_stale_samples_weigh_nothing_and_do_not_count() -> None:
    samples = [sample("1", 2.0), sample("2", 2.0), sample("3", 9.0, age=365)]
    estimate = recalibrate(samples, 4.0, 12.0)
    assert estimate.n == 2 and estimate.state == "catalog"
    assert estimate.listing_ids == ("1", "2")


def test_big_samples_outweigh_small_ones_and_grade_b_weighs_less() -> None:
    assert sample("a", 1, views=10_000).weight < sample("b", 1, views=100_000).weight
    assert sample("c", 1, grade_="B").weight < sample("d", 1, grade_="A").weight


# --- derivados y banderas del código -------------------------------------------------------------


def api(created: str = "2020-01-01", views: tuple[tuple[str, int], ...] = ()) -> ApiEvidence:
    return ApiEvidence(
        fetched_at=NOW,
        channel_id="UC" + "a" * 22,
        created_at=datetime.fromisoformat(created + "T00:00:00+00:00"),
        total_views=1000,
        video_count=len(views),
        recent_videos=tuple(
            RecentVideo(
                video_id=f"v{i}",
                title="t",
                published_at=datetime.fromisoformat(day + "T00:00:00+00:00"),
                duration_seconds=600,
                views=count,
            )
            for i, (day, count) in enumerate(views)
        ),
    )


def test_monthly_views_lower_bound_counts_only_the_last_ninety_days() -> None:
    evidence = api(views=(("2026-10-01", 3000), ("2026-08-15", 6000), ("2025-01-01", 999_999)))
    assert monthly_views_lower_bound(evidence, NOW) == Decimal(3000)
    assert monthly_views_lower_bound(None, NOW) is None


def test_a_video_of_180_seconds_or_less_is_a_short() -> None:
    video = api(views=(("2026-10-01", 1),)).recent_videos[0]
    assert not video.is_short
    assert video.model_copy(update={"duration_seconds": 180}).is_short


def flags(doc: dict[str, Any], **kwargs: Any) -> set[str]:
    evidence = parse(doc)
    primary = select_primary(observation_sets(evidence, {}, TODAY))
    return {
        f.code
        for f in code_risk_flags(
            evidence,
            primary,
            declared_income=kwargs.pop("declared_income", None),
            observed_monthly=kwargs.pop("observed_monthly", None),
            api=kwargs.pop("api", None),
            now=NOW,
            **kwargs,
        )
    }


def test_code_flags_follow_the_documented_thresholds() -> None:
    assert flags(base()) == set()
    assert "declared_income_unsupported" in flags(
        base(), declared_income=Decimal(1000), observed_monthly=Decimal(300)
    )
    assert "single_video_dependence" in flags(base(), top1_revenue_share=0.91)
    assert "new_channel" in flags(base(), api=api(created="2026-08-01"))
    assert "declining_traffic" in flags(base(), previous_views=200_000)
    assert "shorts_dominant" in flags(base(), shorts_share_of_views=0.6)
    doc = base()
    doc["monetization"]["payments_status"] = "setup_in_progress"
    doc["identity_check"]["manager_not_owner_seen"] = True
    assert {"payments_not_configured", "manager_not_owner"} <= flags(doc)


def test_old_captures_and_foreign_currency_are_flagged() -> None:
    doc = base()
    doc["images"][0]["captured_on"] = "2024-07-18"
    assert "stale_capture" in flags(doc)
    doc = base()
    doc["earnings"][0]["amount"] = {"value": "100", "currency": "EUR"}
    doc["earnings"][0]["raw_text"] = "EUR 100"
    evidence = parse(doc)
    fx = {("EUR", date(2026, 10, 26)): Decimal("1.1")}
    primary = select_primary(observation_sets(evidence, fx, TODAY))
    codes = {
        f.code
        for f in code_risk_flags(
            evidence, primary, declared_income=None, observed_monthly=None, api=None, now=NOW
        )
    }
    assert "foreign_currency" in codes


def test_the_contract_example_keeps_its_published_numbers() -> None:
    """Vintage Nostalgia (docs/contracts/listing-evidence-v1.md §13): grado C por antigüedad."""
    doc = deepcopy(base())
    doc["images"][0].update(captured_on="2024-07-18", captured_on_basis="inferred_from_period_end")
    window = period("last_28d", "2024-06-21", "2024-07-18")
    doc["earnings"][0]["period"] = window
    doc["views"][0]["period"] = window
    doc["identity_check"] = {
        "matches_listing_title": "cannot_tell",
        "matches_api_channel": "cannot_tell",
    }
    evidence = parse(doc)
    sets = observation_sets(evidence, {}, TODAY)
    primary = select_primary(sets)
    assert primary is not None and primary.capture_age_days == 832
    assert round(primary.rpm_usd, 3) == Decimal("4.235")
    assert round(primary.monthly_revenue_usd, 1) == Decimal("320.9")  # type: ignore[arg-type]
    assert round(primary.monthly_revenue_usd / Decimal(375), 3) == Decimal("0.856")  # type: ignore[operator]
    assert grade(evidence, primary, sets, has_api_views=False) == "C"
    assert not rpm_sample_eligible(primary, evidence, "C")
