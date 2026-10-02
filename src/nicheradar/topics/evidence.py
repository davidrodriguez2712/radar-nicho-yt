"""Bounded grouping and provenance-aware correspondence between runs."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, insert, select

from nicheradar.config import Settings
from nicheradar.integrations.contracts import Video
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record
from nicheradar.repositories.schema import topic_artifact_sources
from nicheradar.topics.grouping import Embedder, TopicGroup, group_topics


@dataclass
class VersionedEmbedder:
    delegate: Embedder
    version: str

    def encode(self, texts: list[str]) -> list[list[float]]:
        return self.delegate.encode(texts)


def grouping_scope(connection: Connection, run_id: UUID, language: str) -> dict[str, str]:
    run = (
        connection.execute(select(s.analysis_runs).where(s.analysis_runs.c.id == run_id))
        .mappings()
        .one()
    )
    return {"profile_id": str(run["profile_id"]), "mode": run["mode"], "language": language}


def scoped_key(family_id: str, group: TopicGroup, scope: dict[str, str]) -> str:
    if group.method in {"provider_category_fallback", "unclassified"}:
        return f"{family_id}:{group.key}"
    suffix = hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()[:16]
    return f"{family_id}:{suffix}:{group.key}"


def prepare_groups(
    connection: Connection,
    videos: tuple[Video, ...],
    family_id: UUID,
    scope: dict[str, str],
    config: Settings,
    embedder: Embedder | None,
    fallback_reason: str | None,
    now: datetime,
    *,
    eligible_ids: set[str] | None = None,
) -> tuple[tuple[TopicGroup, ...], dict[str, Any]]:
    bounded = tuple(
        sorted({video.id: video for video in videos}.values(), key=lambda item: item.id)
    )[: config.topic_maximum_videos]
    parameters = {
        "algorithm": "bounded-greedy-v2",
        "minimum": config.topic_minimum_size,
        "threshold": config.topic_similarity_threshold,
        "relevance_threshold": config.topic_relevance_threshold,
        "maximum_videos": config.topic_maximum_videos,
        "maximum_text_chars": config.topic_maximum_text_chars,
        "model_version": embedder.version if embedder else None,
    }
    method = (
        "embedding:" + hashlib.sha256(json.dumps(parameters, sort_keys=True).encode()).hexdigest()
    )
    previous: tuple[TopicGroup, ...] = ()
    previous_artifacts: dict[str, str] = {}
    if embedder is not None:
        expired_sources = (
            select(topic_artifact_sources.c.artifact_id)
            .join(
                s.raw_observations,
                s.raw_observations.c.id == topic_artifact_sources.c.observation_id,
            )
            .where(s.raw_observations.c.retain_until <= now)
        )
        rows = (
            connection.execute(
                select(s.topic_artifacts)
                .join(s.topics, s.topics.c.id == s.topic_artifacts.c.topic_id)
                .where(
                    s.topics.c.family_id == family_id,
                    s.topic_artifacts.c.retain_until > now,
                    s.topic_artifacts.c.id.not_in(expired_sources),
                    s.topic_artifacts.c.data["scope"].contains(scope),
                    s.topic_artifacts.c.data["group"]["method"].astext == method,
                    s.topic_artifacts.c.data["group"]["ambiguous_matches"] == [],
                )
                .distinct(s.topic_artifacts.c.topic_id)
                .order_by(
                    s.topic_artifacts.c.topic_id,
                    s.topic_artifacts.c.created_at.desc(),
                    s.topic_artifacts.c.id,
                )
                .limit(201)
            )
            .mappings()
            .all()
        )
        if len(rows) > 200:
            # Truncating matching candidates could turn an ambiguous match into a unique one.
            embedder, fallback_reason = None, "history_limit"
        else:
            previous = tuple(TopicGroup.model_validate(row["data"]["group"]) for row in rows)
            previous_artifacts = {row["data"]["group"]["key"]: str(row["id"]) for row in rows}
    try:
        eligible = tuple(
            video for video in bounded if eligible_ids is None or video.id in eligible_ids
        )
        groups = group_topics(
            eligible if embedder else bounded,
            embedder=VersionedEmbedder(embedder, method) if embedder else None,
            minimum=config.topic_minimum_size,
            threshold=config.topic_similarity_threshold,
            maximum_videos=config.topic_maximum_videos,
            previous=previous,
            maximum_text_chars=config.topic_maximum_text_chars,
        )
        rejected = tuple(
            video.id
            for video in bounded
            if eligible_ids is not None and video.id not in eligible_ids
        )
        if embedder and rejected:
            groups += (
                TopicGroup(
                    key="unverified:" + hashlib.sha256(",".join(rejected).encode()).hexdigest(),
                    label=None,
                    member_ids=rejected,
                    method="unclassified",
                ),
            )
    except (ValueError, RuntimeError, OSError, ImportError):
        groups = group_topics(
            bounded, minimum=config.topic_minimum_size, maximum_videos=config.topic_maximum_videos
        )
        fallback_reason = "embedding_failed"
    metadata = {
        "parameters": parameters,
        "scope": scope,
        "fallback_reason": fallback_reason,
        "received": len(videos),
        "processed": len(bounded),
        "omitted": max(0, len(videos) - len(bounded)),
        "previous_artifacts": previous_artifacts,
    }
    return groups, metadata


def store_group(
    connection: Connection,
    topic_id: UUID,
    run_id: UUID,
    group: TopicGroup,
    metadata: dict[str, Any],
    sources: dict[UUID, datetime],
    now: datetime,
) -> UUID:
    source_ids = sorted(sources, key=str)
    previous_artifacts = metadata.get("previous_artifacts", {})
    correspondence_keys = group.ambiguous_matches or (group.key,)
    data = {key: value for key, value in metadata.items() if key != "previous_artifacts"}
    data["correspondences"] = [
        {
            "artifact_id": previous_artifacts[key],
            "topic_key": key,
            "kind": "ambiguous" if group.ambiguous_matches else "unique",
        }
        for key in correspondence_keys
        if key in previous_artifacts
    ]
    artifact_id = insert_record(
        connection,
        "topic_artifacts",
        {
            "topic_id": topic_id,
            "observation_id": source_ids[0],
            "data": data | {"group": group.model_dump(mode="json"), "run_id": str(run_id)},
            "retain_until": min(sources.values()),
            "created_at": now,
        },
    )
    connection.execute(
        insert(topic_artifact_sources),
        [{"artifact_id": artifact_id, "observation_id": source_id} for source_id in source_ids],
    )
    return artifact_id
