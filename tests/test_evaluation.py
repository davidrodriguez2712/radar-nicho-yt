import asyncio
from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from nicheradar.discovery.sampling import sample, selection_terms
from nicheradar.domain.production import (
    FIT_WEIGHTS,
    STAGES,
    EstimateRange,
    FitAnchor,
    ProductionStage,
    Recipe,
    rubric_score,
)
from nicheradar.domain.profile import CreatorProfile, VideoFormat
from nicheradar.features.metrics import ViewSnapshot, calculate, observed_trend
from nicheradar.integrations.contracts import Operation, Video
from nicheradar.integrations.synthetic import SyntheticProvider
from nicheradar.recommendations.explanations import explain
from nicheradar.scoring.market import References, evaluate_market
from nicheradar.services.scenarios import Proposal, Scenario, SharedTool, simulate
from tests.test_persistence import NOW


def fixture_videos(format: str = "long") -> tuple[Video, ...]:
    provider = SyntheticProvider()
    return tuple(
        video
        for index in range(6)
        for video in asyncio.run(
            provider.fetch(
                operation=Operation.CHANNEL_VIDEOS,
                parameters={
                    "channelId": f"synthetic:science:channel-{index}",
                    "videoFormat": format,
                },
                now=NOW,
            )
        ).videos
    )


def test_selection_terms_use_specific_query_words_and_family_variants() -> None:
    assert selection_terms("culture", "world cultures") == ("culture", "cultures")
    assert selection_terms("science", "science explained") == ("science", "sciences")


def test_samples_relevance_language_format_dedup() -> None:
    videos = fixture_videos()
    wrong = videos[0].model_copy(
        update={"id": "personal", "title": "Personal space explained", "category": None}
    )
    members = sample(
        (*videos, videos[0], wrong),
        now=NOW,
        format=VideoFormat.LONG,
        language="en",
        terms=("science", "astronomy"),
        selection_method="recent",
    )
    assert len(members) == 49
    assert sum(member.included for member in members) == 42
    assert members[-1].reason == "irrelevant"
    assert sum(member.reason == "format_unknown" for member in members) == 6
    assert {member.size_stratum for member in members} == {"small", "large"}
    shorts = sample(
        videos,
        now=NOW,
        format=VideoFormat.SHORTS,
        language="en",
        terms=("science",),
        selection_method="recent",
    )
    assert not any(member.included for member in shorts)


def test_semantic_match_confirms_only_lexically_unknown_video() -> None:
    source = fixture_videos()[0]
    unknown = source.model_copy(
        update={"id": "semantic", "title": "A distant galaxy", "category": None}
    )
    excluded = source.model_copy(
        update={"id": "excluded", "title": "Personal space for a small apartment", "category": None}
    )
    members = sample(
        (unknown, excluded),
        now=NOW,
        format=VideoFormat.LONG,
        language="en",
        terms=("astronomy",),
        selection_method="recent",
        semantic_matches=frozenset({"semantic", "excluded"}),
    )
    assert members[0].reason == "confirmed"
    assert members[1].reason == "irrelevant"


def test_baseline_minimums_and_outlier_denominator() -> None:
    videos = fixture_videos()
    members = sample(
        videos,
        now=NOW,
        format=VideoFormat.LONG,
        language="en",
        terms=("science",),
        selection_method="recent",
    )
    metrics = calculate(members, NOW)
    assert metrics.videos == 42
    assert metrics.channels == 6
    assert metrics.breakout_classified == 28
    assert metrics.breakout_channels == 4
    assert metrics.breakout_rate == pytest.approx(1 / 7)
    assert metrics.breakout_coverage == 1
    outliers = sample(
        videos,
        now=NOW,
        format=VideoFormat.LONG,
        language="en",
        terms=("science",),
        selection_method="outliers",
    )
    assert calculate(outliers, NOW).breakout_rate is None
    assert calculate(members[:5], NOW).breakout_classified == 0


def test_hand_calculable_metrics_and_zero_subscribers() -> None:
    videos = tuple(
        Video(
            id=f"v-{index}",
            channel_id="a" if index < 2 else "b",
            title="Science",
            published_at=NOW - timedelta(days=10),
            views=views,
            subscriber_count=0,
            format=VideoFormat.LONG,
            language="en",
            category="science",
        )
        for index, views in enumerate([100, 100, 200])
    )
    metrics = calculate(
        sample(
            videos,
            now=NOW,
            format=VideoFormat.LONG,
            language="en",
            terms=("science",),
            selection_method="recent",
        ),
        NOW,
    )
    assert metrics.demand_by_age == {"8-30": 10}
    assert metrics.supply == {"7": 0, "30": 3, "90": 3}
    assert metrics.hhi == 0.5
    assert metrics.concentration_score == 100
    assert metrics.top5_share == 1
    assert all(value is None for value in metrics.views_subscriber_ratios.values())
    # Channel "b" (200 views/10 days = 20/day) outpaces channel "a" (100/10 = 10/day each).
    assert metrics.best_channel_views_per_day == 20
    assert metrics.worst_channel_views_per_day == 10


def test_temporal_change_requires_equivalent_observed_intervals() -> None:
    snapshots = tuple(
        ViewSnapshot(observed_at=NOW + timedelta(days=index), views={"a": views})
        for index, views in enumerate([100, 200, 400])
    )
    assert observed_trend(snapshots) == 1
    assert observed_trend(snapshots[:1]) is None
    assert observed_trend((snapshots[0], snapshots[0], snapshots[2])) is None
    assert (
        observed_trend(
            (
                snapshots[0],
                snapshots[1],
                snapshots[2].model_copy(update={"views": {"different-cohort": 400}}),
            )
        )
        is None
    )


def test_references_are_frozen_and_synthetic_cannot_calibrate_live() -> None:
    metrics = calculate(
        sample(
            fixture_videos(),
            now=NOW,
            format=VideoFormat.LONG,
            language="en",
            terms=("science",),
            selection_method="recent",
        ),
        NOW,
    )
    references = References(
        version="synthetic-v1",
        format=VideoFormat.LONG,
        source="fixture",
        synthetic=True,
        reviewed=True,
        demand_p90_by_age={"8-30": 100},
    )
    evaluation = evaluate_market(metrics, VideoFormat.LONG, references, synthetic=True)
    assert evaluation.score is not None
    assert evaluation.state == "provisional"
    assert evaluation.missing == ("T", "M")
    assert evaluation == evaluate_market(metrics, VideoFormat.LONG, references, synthetic=True)
    live = evaluate_market(metrics, VideoFormat.LONG, references, synthetic=False)
    assert live.state == "uncalibrated"
    assert live.score is None
    assert evaluate_market(metrics, VideoFormat.SHORTS, references, synthetic=True).score is None
    with pytest.raises(ValidationError):
        References(
            version="bad",
            format=VideoFormat.LONG,
            source="invalid",
            synthetic=True,
            reviewed=True,
            demand_p90_by_age={"8-30": 0},
        )


def fixture_recipe() -> Recipe:
    stages = tuple(
        ProductionStage.model_validate(
            {
                "name": name,
                "source": "manual synthetic estimate",
                "variable_usd_per_video": {
                    "low": 5 if name == "editing" else 0,
                    "high": 5 if name == "editing" else 0,
                },
                "human_hours_per_video": {"low": ".1", "high": ".1"},
                "automation": "ai",
                "tool_key": "voice" if name == "voice" else None,
                "tool_units_per_video": 5 if name == "voice" else None,
                "tool_capacity_unit": "synthetic minutes" if name == "voice" else None,
            }
        )
        for name in STAGES
    )
    return Recipe(
        key="fixture",
        version="v1",
        format=VideoFormat.LONG,
        stages=stages,
        rework_margin=Decimal(0),
        anchors={key: FitAnchor(grade=75, evidence="fixture") for key in FIT_WEIGHTS},
    )


def test_fit_requires_all_stages_and_evidence() -> None:
    recipe = fixture_recipe()
    assert rubric_score(recipe) == 75
    assert rubric_score(recipe.model_copy(update={"stages": recipe.stages[:-1]})) is None
    missing = recipe.stages[0].model_copy(update={"variable_usd_per_video": None})
    assert rubric_score(recipe.model_copy(update={"stages": (missing, *recipe.stages[1:])})) is None
    assert recipe.rights_review == "pending"


def fixture_scenario() -> Scenario:
    return Scenario(
        name="two channels",
        proposals=tuple(
            Proposal(
                channel_key=f"channel-{index}",
                opportunity_keys=(f"opportunity-{index}",),
                recipe=fixture_recipe(),
                videos_per_month=4,
            )
            for index in range(2)
        ),
        tools=(
            SharedTool(
                key="voice",
                monthly_usd=EstimateRange(low=Decimal(10), high=Decimal(10)),
                monthly_capacity=Decimal(40),
                capacity_unit="synthetic minutes",
                source="synthetic price",
            ),
        ),
        radar_monthly_usd=EstimateRange(low=Decimal(10), high=Decimal(10)),
        reserve_usd=Decimal(10),
    )


def test_multichannel_subscription_once_capacity_added_no_real_spend() -> None:
    result = simulate(fixture_scenario(), CreatorProfile())
    assert result.status == "viable"
    assert result.channel_count == 2
    assert result.monthly_usd == EstimateRange(low=Decimal(70), high=Decimal(70))
    assert result.tool_usage == {"voice": Decimal(40)}
    assert result.estimates_only
    assert result.monthly_hours_available == 65


def test_scenario_range_unknown_and_joint_limits() -> None:
    scenario = fixture_scenario()
    limited = scenario.model_copy(
        update={"tools": (scenario.tools[0].model_copy(update={"monthly_capacity": Decimal(30)}),)}
    )
    assert simulate(limited, CreatorProfile()).status == "not_viable"
    unknown = scenario.model_copy(update={"radar_monthly_usd": None})
    assert simulate(unknown, CreatorProfile()).status == "not_evaluable"
    assert simulate(unknown, CreatorProfile()).monthly_usd is None
    expensive = scenario.model_copy(
        update={"radar_monthly_usd": EstimateRange(low=Decimal(0), high=Decimal(140))}
    )
    assert simulate(expensive, CreatorProfile()).status == "not_viable"


def test_explanation_cannot_invent_claims_or_mutate_numbers() -> None:
    metrics = calculate(
        sample(
            fixture_videos(),
            now=NOW,
            format=VideoFormat.LONG,
            language="en",
            terms=("science",),
            selection_method="recent",
        ),
        NOW,
    )
    evaluation = evaluate_market(metrics, VideoFormat.LONG, None, synthetic=True)
    explanation = explain(
        evaluation,
        ("evidence-fixture",),
        Decimal(75),
        selector=lambda _: ["invented_rpm"],
        reserved_usd=Decimal(1),
        maximum_llm_usd=Decimal(1),
    )
    assert explanation.enrichment == "deterministic_fallback"
    assert all(claim.evidence_ids == ("evidence-fixture",) for claim in explanation.claims)
    assert explanation.final_score is None
    assert "invented_rpm" not in explanation.model_dump_json()
