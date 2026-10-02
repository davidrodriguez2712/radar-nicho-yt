from datetime import timedelta

import pytest
from sqlalchemy import Connection, select, update

from nicheradar.domain.profile import VideoFormat
from nicheradar.integrations.contracts import Video
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import ConflictError
from nicheradar.services.backlog import (
    append_evaluation,
    decide,
    describe_change,
    latest_decision,
    opportunity_identity,
)
from nicheradar.topics.grouping import TopicGroup, group_topics
from tests.test_evaluation import fixture_videos
from tests.test_persistence import NOW, seed_evidence


class FixtureEmbedder:
    version = "synthetic-vectors-v1"

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [
            [1, 0] if "astronomy" in text else [0, 1] if "history" in text else [-1, 0]
            for text in texts
        ]


def test_grouping_known_topics_noise_and_fallback() -> None:
    videos = tuple(
        Video(id=f"{topic}-{index}", channel_id="fixture", title=topic, published_at=NOW)
        for topic, count in [("astronomy", 3), ("history", 3), ("noise", 1)]
        for index in range(count)
    )
    groups = group_topics(videos, embedder=FixtureEmbedder())
    assert len(groups) == 3
    assert sum(group.method == "noise" for group in groups) == 1
    assert all(group.label is None for group in groups)
    fallback = group_topics(fixture_videos())
    assert fallback[0].method == "provider_category_fallback"
    assert fallback[0].label == "science"
    unknown = group_topics(videos)
    assert unknown[0].method == "unclassified"
    assert unknown[0].label is None


def test_grouping_ambiguous_correspondence_not_automatically_merged() -> None:
    videos = tuple(
        Video(id=str(index), channel_id="fixture", title="astronomy", published_at=NOW)
        for index in range(3)
    )
    previous = tuple(
        TopicGroup(
            key=key,
            label="Different labels do not define identity",
            member_ids=(),
            method="synthetic-vectors-v1",
            centroid=(1, 0),
        )
        for key in ("old-one", "old-two")
    )
    group = group_topics(videos, embedder=FixtureEmbedder(), previous=previous)[0]
    assert group.ambiguous_matches == ("old-one", "old-two")
    assert group.key not in {"old-one", "old-two"}
    assert (
        group_topics(videos, embedder=FixtureEmbedder(), previous=previous[:1])[0].key == "old-one"
    )


@pytest.mark.postgres
def test_backlog_versions_and_decisions_are_independent(db: Connection) -> None:
    ids = seed_evidence(db)
    first = opportunity_identity(db, ids["topic"], "english-learners", "en", VideoFormat.LONG)
    assert first == ids["opportunity"]
    decide(db, first, "dismissed", "Personal decision", 0, NOW)
    db.execute(
        update(s.topics).where(s.topics.c.id == ids["topic"]).values(label="A renamed topic")
    )
    assert (
        opportunity_identity(db, ids["topic"], "english-learners", "en", VideoFormat.LONG) == first
    )
    for _ in range(2):
        append_evaluation(
            db,
            first,
            {
                "cohort_id": ids["cohort"],
                "run_id": ids["run"],
                "method_version": "synthetic-v1",
                "state": "uncalibrated",
                "confidence": "provisional",
                "retain_until": NOW + timedelta(days=1),
            },
        )
    assert latest_decision(db, first)["state"] == "dismissed"
    assert db.execute(
        select(s.evaluation_versions.c.version).order_by(s.evaluation_versions.c.version)
    ).scalars().all() == [1, 2]
    with pytest.raises(ConflictError):
        decide(db, first, "selected", "stale edit", 0, NOW)
    second = opportunity_identity(db, ids["topic"], "english-learners", "en", VideoFormat.SHORTS)
    decide(db, first, "selected", "research only", 1, NOW)
    decide(db, second, "selected", "same future channel, another format", 0, NOW)
    assert latest_decision(db, first)["state"] == latest_decision(db, second)["state"] == "selected"


def test_history_distinguishes_method_data_and_relative_rank() -> None:
    previous = {"method_version": "v1", "market_score": 50}
    assert describe_change(previous, previous, 1, 2) == ["relative_rank_changed"]
    assert describe_change(previous, previous | {"method_version": "v2"}) == ["method_changed"]
    assert describe_change(previous, previous | {"market_score": 60}) == [
        "evidence_or_assumptions_changed"
    ]
