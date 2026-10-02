from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine, select, update

from nicheradar.discovery.sampling import sample
from nicheradar.domain.profile import VideoFormat
from nicheradar.features.history import Observation, load_history, summarize_history
from nicheradar.features.metrics import calculate
from nicheradar.integrations.contracts import Batch, Operation, Video
from nicheradar.integrations.retention import expire
from nicheradar.integrations.synthetic import SyntheticProvider
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record
from nicheradar.services.backlog import decide
from tests.test_discovery import run_pipeline
from tests.test_persistence import NOW, seed_evidence


def points(values: list[int | None], days: list[float] | None = None) -> tuple[Observation, ...]:
    offsets = days if days is not None else list(range(len(values)))
    return tuple(
        reversed(
            [
                Observation(NOW + timedelta(days=offset), value, uuid4(), NOW + timedelta(days=30))
                for offset, value in zip(offsets, values, strict=True)
            ]
        )
    )


@pytest.mark.parametrize(
    "values,reason,change",
    [
        ([100], "fewer_than_two_observations", None),
        ([100, 200], "fewer_than_three_observations", None),
        ([100, 200, 400], None, 1),
        ([100, 200, 250], None, -0.5),
        ([100, 100, 200], "zero_previous_velocity", None),
        ([100, 90, 200], "counts_revised_downwards", None),
        ([100, 200, 90], "counts_revised_downwards", None),
        ([100, None, 400], "unknown_or_conflicting_counts", None),
    ],
)
def test_temporal_requirements(
    values: list[int | None], reason: str | None, change: float | None
) -> None:
    key = uuid4()
    result = summarize_history({key: points(values)}, {key}, 0.1)
    assert result["reason"] == reason
    assert result["trend_relative_change"] == change
    if len(values) == 2:
        assert result["observed_views_change"] == 100
        assert result["recent_views_per_day"] == 100


def test_interval_equivalence_alignment_and_partial_panel() -> None:
    first, second = uuid4(), uuid4()
    history = {first: points([100, 200, 400], [0, 1, 2.05])}
    assert summarize_history(history, {first}, 0.1)["trend_relative_change"] == pytest.approx(
        200 / 1.05 / 100 - 1
    )
    assert summarize_history(history, {first}, 0)["reason"] == "non_equivalent_intervals"
    history[second] = points([100, 200, 400], [1, 2, 3])
    assert (
        summarize_history(history, {first, second}, 0.1)["reason"]
        == "unaligned_observation_windows"
    )
    history[second] = points([400])
    result = summarize_history(history, {first, second}, 0.1)
    assert result["coverage"] == 0.5
    assert result["trend_relative_change"] is None


@pytest.mark.parametrize(
    "values,expected_hhi,expected_top",
    [
        ([100], None, None),
        ([0, 0], None, None),
        ([100, 0], 1, 1),
        ([100, 100], 0.5, 1),
        ([100] * 6, 1 / 6, 5 / 6),
    ],
)
def test_concentration_minimum_and_known_distributions(
    values: list[int], expected_hhi: float | None, expected_top: float | None
) -> None:
    videos = tuple(
        Video(
            id=str(index),
            channel_id=str(index),
            title="science",
            category="science",
            published_at=NOW - timedelta(days=10),
            views=views,
            language="en",
            format=VideoFormat.LONG,
        )
        for index, views in enumerate(values)
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
    assert (
        metrics.hhi == pytest.approx(expected_hhi)
        if expected_hhi is not None
        else metrics.hhi is None
    )
    assert (
        metrics.top5_share == pytest.approx(expected_top)
        if expected_top is not None
        else metrics.top5_share is None
    )


class GrowingProvider(SyntheticProvider):
    async def fetch(self, operation: Operation, parameters: dict[str, Any], now: datetime) -> Batch:
        batch = await super().fetch(operation, parameters, now)
        elapsed = (now - NOW).days
        multiplier = [100, 200, 400][min(elapsed, 2)]
        return batch.model_copy(
            update={
                "videos": tuple(
                    video.model_copy(
                        update={
                            "views": multiplier,
                            "published_at": NOW - timedelta(days=10),
                        }
                    )
                    for video in batch.videos
                )
            }
        )


@pytest.mark.postgres
def test_pipeline_observes_growth_and_expires_historical_derivatives(
    isolated_engine: Engine,
) -> None:
    provider = GrowingProvider()
    run_pipeline(isolated_engine, NOW, provider)
    with isolated_engine.begin() as connection:
        opportunity = connection.execute(
            select(s.opportunities.c.id).where(s.opportunities.c.format == "long")
        ).scalar_one()
        decide(connection, opportunity, "selected", "Observe", 0, NOW)
        first = (
            connection.execute(
                select(s.evaluation_versions).where(
                    s.evaluation_versions.c.opportunity_id == opportunity
                )
            )
            .mappings()
            .one()
        )
        assert first["explanation"]["temporal"]["trend_relative_change"] is None
        original_sources = set(
            connection.execute(
                select(s.evidence_links.c.observation_id).where(
                    s.evidence_links.c.evaluation_id == first["id"]
                )
            ).scalars()
        )
        # Initial topic grouping uses both formats; temporal evidence must only
        # reuse the long-form sources for the opportunity being refreshed.
        original_sources = {
            row["id"]
            for row in connection.execute(
                select(s.raw_observations).where(s.raw_observations.c.id.in_(original_sources))
            ).mappings()
            if row["payload"]["videos"][0]["format"] == "long"
        }
        assert len(original_sources) == 6
    run_pipeline(isolated_engine, NOW + timedelta(days=1), provider)
    run_pipeline(isolated_engine, NOW + timedelta(days=2), provider)
    with isolated_engine.begin() as connection:
        latest = (
            connection.execute(
                select(s.evaluation_versions)
                .where(s.evaluation_versions.c.opportunity_id == opportunity)
                .order_by(s.evaluation_versions.c.version.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        assert latest["explanation"]["temporal"]["trend_relative_change"] == 1
        assert latest["explanation"]["metrics"]["trend_relative_change"] == 1
        assert latest["market_score"] is None  # History is not calibration.
        assert latest["explanation"]["temporal"]["panel_videos"] == 42
        linked = set(
            connection.execute(
                select(s.evidence_links.c.observation_id).where(
                    s.evidence_links.c.evaluation_id == latest["id"]
                )
            ).scalars()
        )
        assert original_sources <= linked
        first_raw = next(iter(original_sources))
        assert first_raw is not None
        expire(connection, NOW + timedelta(days=2), revoked_observation_ids=(first_raw,))
        expired = (
            connection.execute(
                select(s.evaluation_versions).where(s.evaluation_versions.c.id == latest["id"])
            )
            .mappings()
            .one()
        )
        assert expired["explanation"] is None
        assert expired["expired_at"] is not None


@pytest.mark.postgres
def test_history_deduplicates_dates_and_does_not_cross_scopes(db: Connection) -> None:
    ids = seed_evidence(db)
    original = dict(
        db.execute(
            select(s.video_observations).where(s.video_observations.c.id == ids["observation"])
        )
        .mappings()
        .one()
    )
    db.execute(
        update(s.video_observations)
        .where(s.video_observations.c.id == ids["observation"])
        .values(observed_at=NOW, views=400)
    )
    original_raw = dict(
        db.execute(select(s.raw_observations).where(s.raw_observations.c.id == ids["raw"]))
        .mappings()
        .one()
    )
    for offset, views in [(0, 400), (-1, 200), (-2, 100)]:
        raw = insert_record(
            db,
            "raw_observations",
            {key: value for key, value in original_raw.items() if key != "id"}
            | {"fetched_at": NOW + timedelta(days=offset)},
        )
        insert_record(
            db,
            "video_observations",
            {key: value for key, value in original.items() if key != "id"}
            | {
                "raw_observation_id": raw,
                "observed_at": NOW + timedelta(days=offset),
                "views": views,
            },
        )
    history = load_history(db, [ids["observation"]], NOW, 90)
    assert len(history[ids["video"]]) == 3
    assert len(history[ids["video"]][0].source_ids) == 2
    assert summarize_history(history, {ids["video"]}, 0.1)["trend_relative_change"] == 1
    # A same-date contradictory observation is not silently selected by UUID ordering.
    raw = insert_record(
        db, "raw_observations", {key: value for key, value in original_raw.items() if key != "id"}
    )
    insert_record(
        db,
        "video_observations",
        {key: value for key, value in original.items() if key != "id"}
        | {"raw_observation_id": raw, "views": 900, "observed_at": NOW},
    )
    assert (
        summarize_history(load_history(db, [ids["observation"]], NOW, 90), {ids["video"]}, 0.1)[
            "reason"
        ]
        == "unknown_or_conflicting_counts"
    )


@pytest.mark.postgres
def test_foreign_source_is_not_history(db: Connection) -> None:
    ids = seed_evidence(db)
    original = dict(
        db.execute(
            select(s.video_observations).where(s.video_observations.c.id == ids["observation"])
        )
        .mappings()
        .one()
    )
    original_raw = dict(
        db.execute(select(s.raw_observations).where(s.raw_observations.c.id == ids["raw"]))
        .mappings()
        .one()
    )
    request = dict(
        db.execute(
            select(s.provider_requests).where(
                s.provider_requests.c.id == original_raw["request_id"]
            )
        )
        .mappings()
        .one()
    )
    for offset in (-1, -2):
        other_request = insert_record(
            db,
            "provider_requests",
            {key: value for key, value in request.items() if key != "id"}
            | {"auth_scope": "different-account", "idempotency_key": str(uuid4())},
        )
        raw = insert_record(
            db,
            "raw_observations",
            {key: value for key, value in original_raw.items() if key != "id"}
            | {"request_id": other_request, "fetched_at": NOW + timedelta(days=offset)},
        )
        insert_record(
            db,
            "video_observations",
            {key: value for key, value in original.items() if key != "id"}
            | {"raw_observation_id": raw, "observed_at": NOW + timedelta(days=offset)},
        )
    assert len(load_history(db, [ids["observation"]], NOW, 90)[ids["video"]]) == 1
