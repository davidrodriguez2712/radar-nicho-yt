"""Tests for the opportunity Score (0-100), computed on the fly from a saved
channel-analysis snapshot. Pure function: no database, no network."""

from nicheradar.services.channel_analysis_scoring import compute_score


def test_score_all_components_present() -> None:
    snapshot = {
        "metrics": {
            "panorama": {
                "status": "computed",
                "metrics": {"hhi": 0.2, "top5_share": 0.5, "breakout_rate": 0.3},
            },
            "matched_advertising_rate": {"low": 3.0, "high": 7.0},
        },
        "comparable_videos": {
            "videos_by_channel": {
                "UC1": [{"views": 5000}, {"views": 3000}],
                "UC2": [{"views": 100000}],
            }
        },
        "growth": {"tier": "measured", "subscribers_per_day": 25, "days_between_observations": 10},
    }
    result = compute_score(snapshot)
    assert result["value"] is not None
    assert 0 <= result["value"] <= 100
    assert set(result["components_used"]) == {
        "concentration",
        "breakout",
        "demand",
        "rpm",
        "growth",
    }


def test_score_without_comparable_videos_excludes_demand() -> None:
    # Snapshot ya expirado por retención (evidence_available=False): la vista de la API
    # pone snapshot=None antes de que compute_score lo vea, así que este caso real nunca
    # llega a compute_score con datos parciales -- lo que SÍ puede faltar aquí es que un
    # snapshot recién persistido nunca tuvo "comparable_videos" poblado con vistas (todas
    # las vistas vinieron None de la API, caso real ya cubierto por fetch_channel_videos).
    snapshot = {
        "metrics": {
            "panorama": {
                "status": "computed",
                "metrics": {"hhi": 0.2, "top5_share": 0.5, "breakout_rate": 0.3},
            },
            "matched_advertising_rate": None,
        },
        "comparable_videos": {"videos_by_channel": {"UC1": [{"views": None}]}},
        "growth": {
            "tier": "insufficient_evidence",
            "subscribers_per_day": None,
            "days_between_observations": None,
        },
    }
    result = compute_score(snapshot)
    assert set(result["components_used"]) == {"concentration", "breakout"}
    assert result["value"] is not None


def test_score_missing_niche_reweights_without_rpm() -> None:
    # No "comparable_videos" key at all -- demand is excluded too, alongside rpm/growth,
    # leaving only concentration + breakout. This covers "demand missing because the key
    # is absent entirely", distinct from the above test's "key present but all views None".
    snapshot = {
        "metrics": {
            "panorama": {
                "status": "computed",
                "metrics": {"hhi": 0.2, "top5_share": 0.5, "breakout_rate": 0.3},
            },
            "matched_advertising_rate": None,
        },
        "growth": {
            "tier": "insufficient_evidence",
            "subscribers_per_day": None,
            "days_between_observations": None,
        },
    }
    result = compute_score(snapshot)
    assert "rpm" not in result["components_used"]
    assert "growth" not in result["components_used"]
    assert "demand" not in result["components_used"]
    assert result["value"] is not None  # los componentes disponibles igual producen un número


def test_score_no_panorama_returns_none() -> None:
    snapshot = {"metrics": {"panorama": {"status": "incomplete", "reason": "no_comparable_videos"}}}
    result = compute_score(snapshot)
    assert result["value"] is None
    assert result["components_used"] == []


def test_score_missing_metrics_key_returns_none() -> None:
    # No "metrics" key at all -- must not raise, must behave like "no panorama".
    result = compute_score({})
    assert result["value"] is None
    assert result["components_used"] == []


def test_score_growth_lifetime_average_uses_same_per_day_formula_as_measured() -> None:
    # Regression for the Task 17 bug: pipeline.py's persist stage stores
    # subscribers_per_day in genuine per-day units for BOTH tiers ("measured":
    # (now - prior) / days; "lifetime_average": subscribers / age_days, age_days also a
    # real day-count, not a year-count). compute_score used to divide "lifetime_average"
    # by an extra 365, crushing its growth component to near-zero versus "measured" for
    # the identical real daily growth rate. Both tiers must produce the identical
    # component value for the same subscribers_per_day.
    base_snapshot = {
        "metrics": {
            "panorama": {
                "status": "computed",
                "metrics": {"hhi": 0.2, "top5_share": 0.5, "breakout_rate": 0.3},
            },
            "matched_advertising_rate": None,
        },
    }
    measured = compute_score(
        base_snapshot
        | {
            "growth": {
                "tier": "measured",
                "subscribers_per_day": 25,
                "days_between_observations": 10,
            }
        }
    )
    lifetime_average = compute_score(
        base_snapshot
        | {
            "growth": {
                "tier": "lifetime_average",
                "subscribers_per_day": 25,
                "days_between_observations": None,
            }
        }
    )
    assert measured["components"]["growth"] == 50.0
    assert lifetime_average["components"]["growth"] == 50.0


def test_score_rpm_and_growth_missing_reweights_across_three() -> None:
    # Both rpm and growth absent simultaneously: value must come purely from
    # concentration + breakout + demand, reweighted (not zero-filled) across those three.
    snapshot = {
        "metrics": {
            "panorama": {
                "status": "computed",
                "metrics": {"hhi": 0.2, "top5_share": 0.5, "breakout_rate": 0.3},
            },
            "matched_advertising_rate": None,
        },
        "comparable_videos": {"videos_by_channel": {"UC1": [{"views": 5000}, {"views": 3000}]}},
        "growth": {
            "tier": "insufficient_evidence",
            "subscribers_per_day": None,
            "days_between_observations": None,
        },
    }
    result = compute_score(snapshot)
    assert set(result["components_used"]) == {"concentration", "breakout", "demand"}
    assert result["value"] is not None

    concentration = result["components"]["concentration"]
    breakout = result["components"]["breakout"]
    demand = result["components"]["demand"]
    expected = (concentration * 25.0 + breakout * 20.0 + demand * 20.0) / (25.0 + 20.0 + 20.0)
    assert result["value"] == round(expected, 1)
