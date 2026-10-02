import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine, func, select, update

from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile, VideoFormat, initial_catalog
from nicheradar.integrations.contracts import Batch, Operation, Video
from nicheradar.integrations.retention import expire
from nicheradar.integrations.synthetic import SyntheticProvider
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.repositories.schema import topic_artifact_sources
from nicheradar.services.backlog import decide, latest_decision
from nicheradar.services.console import opportunity_detail
from nicheradar.topics.evidence import prepare_groups, store_group
from nicheradar.topics.grouping import (
    Embedder,
    LocalOnnxEmbedder,
    TopicGroup,
    group_topics,
    semantic_relevance,
)
from nicheradar.topics.runtime import configured_embedder
from nicheradar.workers.pipeline import Pipeline
from nicheradar.workers.queue import claim, enqueue
from tests.test_persistence import NOW, seed_evidence
from tests.test_topics_backlog import FixtureEmbedder


class TopicProvider(SyntheticProvider):
    async def fetch(self, operation: Operation, parameters: dict[str, Any], now: datetime) -> Batch:
        batch = await super().fetch(operation, parameters, now)
        videos = []
        for video in batch.videos:
            index = int(video.id.rsplit("-", 1)[-1])
            topic = "astronomy" if index < 3 else "history"
            if index == 6 and video.channel_id.endswith("channel-0"):
                topic = "noise"
            videos.append(video.model_copy(update={"title": topic}))
        return batch.model_copy(update={"videos": tuple(videos)})


def execute(
    engine: Engine,
    now: datetime,
    embedder: Embedder | None,
    config: Settings | None = None,
    *,
    expected_status: str = "succeeded",
) -> dict[str, Any]:
    with engine.begin() as connection:
        profile = seed_profile(
            connection, CreatorProfile(formats=(VideoFormat.LONG,)), initial_catalog()
        )
        job_id = enqueue(connection, profile, str(uuid4()), now, {})
        assert claim(connection, "topic-test", now)
    asyncio.run(
        Pipeline(
            engine,
            clock=lambda: now,
            provider=TopicProvider(),
            embedder=embedder,
            settings=config,
        ).process(job_id, "topic-test")
    )
    with engine.connect() as connection:
        job = dict(connection.execute(select(s.jobs).where(s.jobs.c.id == job_id)).mappings().one())
        assert job["status"] == expected_status
        return job


@pytest.mark.postgres
def test_pipeline_groups_noise_and_refresh_preserves_identity(isolated_engine: Engine) -> None:
    first = execute(isolated_engine, NOW, FixtureEmbedder())
    with isolated_engine.begin() as connection:
        artifacts = connection.execute(select(s.topic_artifacts)).mappings().all()
        assert len(artifacts) == 4  # Two supported groups, one noise, one unverified.
        assert (
            sum(row["data"]["group"]["method"].startswith("embedding:") for row in artifacts) == 2
        )
        assert all(row["data"]["group"]["label"] is None for row in artifacts)
        supported = next(
            row for row in artifacts if row["data"]["group"]["method"].startswith("embedding:")
        )
        opportunity = connection.execute(
            select(s.opportunities.c.id).where(s.opportunities.c.topic_id == supported["topic_id"])
        ).scalar_one()
        decide(connection, opportunity, "selected", "Research only", 0, NOW)
        for row in artifacts:
            if row["data"]["group"]["method"] in {"noise", "unclassified"}:
                evaluation = (
                    connection.execute(
                        select(s.evaluation_versions)
                        .join(
                            s.opportunities,
                            s.opportunities.c.id == s.evaluation_versions.c.opportunity_id,
                        )
                        .where(s.opportunities.c.topic_id == row["topic_id"])
                    )
                    .mappings()
                    .one()
                )
                assert evaluation["state"] == "insufficient_evidence"
                assert evaluation["market_score"] is None
        assert "astronomy" not in str(first["checkpoints"])
        assert "centroid" not in str(first["checkpoints"])
    second = execute(isolated_engine, NOW + timedelta(days=1), FixtureEmbedder())
    assert second["checkpoints"]["planning"]["opportunity_id"] == str(opportunity)
    with isolated_engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count())
                .select_from(s.evaluation_versions)
                .where(s.evaluation_versions.c.opportunity_id == opportunity)
            ).scalar_one()
            == 2
        )
        assert latest_decision(connection, opportunity)["state"] == "selected"
        detail = opportunity_detail(connection, opportunity, NOW + timedelta(days=1))
        assert detail is not None
        assert detail["grouping"]["correspondences"][0]["kind"] == "unique"
        assert "centroid" not in detail["grouping"]
        assert (
            connection.execute(select(func.count()).select_from(s.opportunities)).scalar_one() == 4
        )


@pytest.mark.postgres
def test_missing_and_broken_model_use_explicit_fallback(
    isolated_engine: Engine, tmp_path: Path
) -> None:
    missing = Settings(
        embedding_model_directory=tmp_path / "absent", embedding_model_version="fixture-v1"
    )
    first = execute(isolated_engine, NOW, None, missing)
    assert first["checkpoints"]["cohort"]["grouping"]["fallback_reason"] == "model_unavailable"

    class BrokenEmbedder(FixtureEmbedder):
        def encode(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("external text must not reach logs or checkpoints")

    second = execute(isolated_engine, NOW + timedelta(days=1), BrokenEmbedder())
    assert second["checkpoints"]["cohort"]["grouping"]["fallback_reason"] == "embedding_failed"
    assert "external text" not in str(second)


@pytest.mark.postgres
def test_grouping_limits_are_reported(isolated_engine: Engine) -> None:
    job = execute(isolated_engine, NOW, FixtureEmbedder(), Settings(topic_maximum_videos=6))
    metadata = job["checkpoints"]["cohort"]["grouping"]
    assert metadata["processed"] == 6
    assert metadata["omitted"] == metadata["received"] - 6


@pytest.mark.postgres
def test_artifact_expires_when_non_anchor_source_is_revoked(db: Connection) -> None:
    ids = seed_evidence(db)
    original = dict(
        db.execute(select(s.raw_observations).where(s.raw_observations.c.id == ids["raw"]))
        .mappings()
        .one()
    )
    second_raw = insert_record(
        db, "raw_observations", {key: value for key, value in original.items() if key != "id"}
    )
    artifact = store_group(
        db,
        ids["topic"],
        ids["run"],
        TopicGroup(
            key="group",
            label=None,
            member_ids=("one", "two"),
            method="fixture",
            centroid=(1, 0),
        ),
        {},
        {ids["raw"]: NOW + timedelta(days=1), second_raw: NOW + timedelta(days=1)},
        NOW,
    )
    anchor = db.execute(
        select(s.topic_artifacts.c.observation_id).where(s.topic_artifacts.c.id == artifact)
    ).scalar_one()
    revoked = second_raw if anchor == ids["raw"] else ids["raw"]
    expire(db, NOW, revoked_observation_ids=(revoked,))
    assert (
        db.execute(
            select(func.count())
            .select_from(s.topic_artifacts)
            .where(s.topic_artifacts.c.id == artifact)
        ).scalar_one()
        == 0
    )
    assert db.execute(select(func.count()).select_from(topic_artifact_sources)).scalar_one() == 0
    assert (
        db.execute(
            select(s.raw_observations.c.id).where(s.raw_observations.c.id == anchor)
        ).scalar_one()
        == anchor
    )


@pytest.mark.postgres
def test_ambiguous_history_and_scope_do_not_merge(db: Connection) -> None:
    ids = seed_evidence(db)
    scope = {"profile_id": str(ids["profile"]), "mode": "synthetic", "language": "en"}
    videos = tuple(
        Video(id=str(index), channel_id="fixture", title="astronomy", published_at=NOW)
        for index in range(3)
    )
    groups, metadata = prepare_groups(
        db, videos, ids["family"], scope, Settings(), FixtureEmbedder(), None, NOW
    )
    for index in range(2):
        topic_id = insert_record(
            db,
            "topics",
            {
                "family_id": ids["family"],
                "identity_key": f"previous-{index}",
                "method_version": groups[0].method,
            },
        )
        store_group(
            db,
            topic_id,
            ids["run"],
            groups[0].model_copy(update={"key": f"previous-{index}"}),
            metadata,
            {ids["raw"]: NOW + timedelta(days=1)},
            NOW,
        )
    ambiguous, _ = prepare_groups(
        db, videos, ids["family"], scope, Settings(), FixtureEmbedder(), None, NOW
    )
    assert ambiguous[0].ambiguous_matches == ("previous-0", "previous-1")
    assert ambiguous[0].key not in ambiguous[0].ambiguous_matches
    isolated, _ = prepare_groups(
        db,
        videos,
        ids["family"],
        scope | {"mode": "live"},
        Settings(),
        FixtureEmbedder(),
        None,
        NOW,
    )
    assert isolated[0].ambiguous_matches == ()
    changed, _ = prepare_groups(
        db,
        videos,
        ids["family"],
        scope,
        Settings(topic_similarity_threshold=0.9),
        FixtureEmbedder(),
        None,
        NOW,
    )
    assert changed[0].ambiguous_matches == ()
    db.execute(
        update(s.raw_observations)
        .where(s.raw_observations.c.id == ids["raw"])
        .values(retain_until=NOW + timedelta(hours=1))
    )
    expired, _ = prepare_groups(
        db,
        videos,
        ids["family"],
        scope,
        Settings(),
        FixtureEmbedder(),
        None,
        NOW + timedelta(hours=2),
    )
    assert expired[0].ambiguous_matches == ()


def test_local_onnx_model_never_downloads_and_uses_one_cpu_thread(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "model.onnx").write_bytes(b"fixture")
    (tmp_path / "tokenizer.json").write_text("{}")
    observed: dict[str, Any] = {}

    class Options:
        intra_op_num_threads = 0
        inter_op_num_threads = 0
        execution_mode: object | None = None

    class Session:
        def __init__(self, path: str, *, sess_options: Options, providers: list[str]):
            observed.update(path=path, options=sess_options, providers=providers)

        def get_inputs(self) -> list[SimpleNamespace]:
            return [SimpleNamespace(name=name) for name in ("input_ids", "attention_mask")]

    class Tokenizer:
        @classmethod
        def from_file(cls, path: str) -> "Tokenizer":
            observed["tokenizer"] = path
            return cls()

        def enable_truncation(self, *, max_length: int) -> None:
            observed["max_length"] = max_length

        def enable_padding(self) -> None:
            observed["padding"] = True

    modules = {
        "numpy": SimpleNamespace(),
        "onnxruntime": SimpleNamespace(
            SessionOptions=Options,
            ExecutionMode=SimpleNamespace(ORT_SEQUENTIAL="sequential"),
            InferenceSession=Session,
        ),
        "tokenizers": SimpleNamespace(Tokenizer=Tokenizer),
    }

    monkeypatch.setattr(
        "nicheradar.topics.grouping.importlib.import_module",
        lambda name: modules[name],
    )
    LocalOnnxEmbedder(tmp_path, "fixture-v1")
    assert observed["path"] == str(tmp_path / "model.onnx")
    assert observed["providers"] == ["CPUExecutionProvider"]
    assert observed["options"].intra_op_num_threads == 1
    assert observed["options"].inter_op_num_threads == 1
    assert observed["options"].execution_mode == "sequential"
    assert observed["max_length"] == 128
    assert observed["padding"] is True
    assert configured_embedder(Settings()) == (None, "model_not_configured")


def test_semantic_relevance_uses_query_similarity_and_bounds() -> None:
    videos = (
        Video(id="space", channel_id="fixture", title="astronomy", published_at=NOW),
        Video(id="history", channel_id="fixture", title="history", published_at=NOW),
    )
    matches, scores = semantic_relevance(
        videos,
        query="astronomy",
        embedder=FixtureEmbedder(),
        threshold=0.8,
        maximum_text_chars=100,
    )
    assert matches == {"space"}
    assert scores == {"history": 0.0, "space": 1.0}
    assert Settings().topic_relevance_threshold == 0.35


def test_vector_validation_and_text_bounds() -> None:
    class InspectEmbedder(FixtureEmbedder):
        def encode(self, texts: list[str]) -> list[list[float]]:
            assert all(len(text) <= 100 for text in texts)
            return [[0, 0] for _ in texts]

    videos = tuple(
        Video(id=str(index), channel_id="fixture", title="astronomy" * 1000, published_at=NOW)
        for index in range(3)
    )
    with pytest.raises(ValueError, match="invalid embedding"):
        group_topics(videos, embedder=InspectEmbedder(), maximum_text_chars=100)


def test_two_new_groups_matching_same_old_group_are_ambiguous() -> None:
    class SplitEmbedder(FixtureEmbedder):
        def encode(self, texts: list[str]) -> list[list[float]]:
            return [[1, 0.7] if "first" in text else [1, -0.7] for text in texts]

    videos = tuple(
        Video(id=f"{topic}-{index}", channel_id="fixture", title=topic, published_at=NOW)
        for topic in ("first", "second")
        for index in range(3)
    )
    groups = group_topics(
        videos,
        embedder=SplitEmbedder(),
        previous=(
            TopicGroup(
                key="old",
                label=None,
                member_ids=(),
                method=SplitEmbedder.version,
                centroid=(1, 0),
            ),
        ),
    )
    assert len(groups) == 2
    assert all(group.ambiguous_matches == ("old",) for group in groups)
    assert len({group.key for group in groups}) == 2


def test_ambiguous_group_cannot_keep_hash_of_existing_members() -> None:
    videos = tuple(
        Video(id=str(index), channel_id="fixture", title="astronomy", published_at=NOW)
        for index in range(3)
    )
    old = group_topics(videos, embedder=FixtureEmbedder())[0]
    group = group_topics(
        videos,
        embedder=FixtureEmbedder(),
        previous=(
            old,
            old.model_copy(update={"key": "another-old-topic"}),
        ),
    )[0]
    assert group.key != old.key
    assert set(group.ambiguous_matches) == {old.key, "another-old-topic"}


@pytest.mark.postgres
def test_ambiguous_refresh_records_evidence_without_replacing_selected_topic(
    isolated_engine: Engine,
) -> None:
    first = execute(isolated_engine, NOW, FixtureEmbedder())
    with isolated_engine.begin() as connection:
        artifacts = connection.execute(select(s.topic_artifacts)).mappings().all()
        artifact = next(
            row for row in artifacts if row["data"]["group"]["method"].startswith("embedding:")
        )
        group = TopicGroup.model_validate(artifact["data"]["group"])
        opportunity = connection.execute(
            select(s.opportunities.c.id).where(s.opportunities.c.topic_id == artifact["topic_id"])
        ).scalar_one()
        decide(connection, opportunity, "selected", "Do not merge", 0, NOW)
        topic = insert_record(
            connection,
            "topics",
            {
                "family_id": first["checkpoints"]["planning"]["family_id"],
                "identity_key": "ambiguous-existing-topic",
                "method_version": group.method,
            },
        )
        store_group(
            connection,
            topic,
            first["run_id"],
            group.model_copy(update={"key": "another-old-topic"}),
            artifact["data"],
            {
                artifact["observation_id"]: artifact["retain_until"],
            },
            NOW,
        )
    job = execute(
        isolated_engine, NOW + timedelta(days=1), FixtureEmbedder(), expected_status="partial"
    )
    assert job["checkpoints"]["cohort"]["grouping"]["ambiguous_groups"] == 1
    with isolated_engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count())
                .select_from(s.evaluation_versions)
                .where(s.evaluation_versions.c.opportunity_id == opportunity)
            ).scalar_one()
            == 1
        )
        recorded = (
            connection.execute(
                select(s.topic_artifacts.c.data).where(
                    s.topic_artifacts.c.data["run_id"].astext == str(job["run_id"])
                )
            )
            .scalars()
            .all()
        )
        assert any(row["group"]["ambiguous_matches"] for row in recorded)
        assert latest_decision(connection, opportunity)["state"] == "selected"
