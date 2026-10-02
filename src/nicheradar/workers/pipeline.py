"""Durable synthetic-first pipeline. Checkpoints contain IDs, never retained provider text."""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, Engine, select, update
from sqlalchemy.dialects.postgresql import insert

from nicheradar.config import Settings
from nicheradar.discovery.planning import finish_work, plan_family
from nicheradar.discovery.queries import collect
from nicheradar.discovery.sampling import sample, selection_terms
from nicheradar.domain.profile import CreatorProfile, VideoFormat
from nicheradar.features.history import temporal_evidence
from nicheradar.features.metrics import calculate
from nicheradar.integrations.contracts import Batch, Operation, Provider, ProviderError, Video
from nicheradar.integrations.synthetic import SyntheticProvider
from nicheradar.recommendations.explanations import snapshot_explanation
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import (
    canonical_platform,
    channel_identity,
    insert_record,
    video_identity,
)
from nicheradar.repositories.schema import topic_artifact_sources
from nicheradar.scoring.advertising import assess_advertising
from nicheradar.scoring.combined import combine
from nicheradar.scoring.market import MarketEvaluation, evaluate_market
from nicheradar.services.backlog import append_evaluation, opportunity_identity
from nicheradar.services.explanations import enrich
from nicheradar.services.gateway import Gateway
from nicheradar.services.pilot import preflight, vidiq_limits, vidiq_provider, vidiq_tariffs
from nicheradar.services.production import (
    ProductionPlan,
    ensure_default_recipe,
    evaluate_plan,
    latest_plan,
)
from nicheradar.services.ranking import capture
from nicheradar.services.scoring import ScoringConfiguration, latest_configuration
from nicheradar.services.youtube_enrichment import (
    youtube_limits,
    youtube_provider,
    youtube_tariffs,
)
from nicheradar.topics.evidence import grouping_scope, prepare_groups, scoped_key, store_group
from nicheradar.topics.grouping import Embedder, semantic_relevance
from nicheradar.topics.runtime import configured_embedder
from nicheradar.workers.queue import confirm_stage, fail_job, heartbeat, owned_job


def utcnow() -> datetime:
    return datetime.now(UTC)


def observations(connection: Connection, raw_ids: list[str], now: datetime) -> list[dict[str, Any]]:
    rows = (
        connection.execute(
            select(s.raw_observations).where(
                s.raw_observations.c.id.in_([UUID(raw_id) for raw_id in raw_ids]),
                s.raw_observations.c.retain_until > now,
            )
        )
        .mappings()
        .all()
    )
    if len(rows) != len(set(raw_ids)):
        raise ProviderError("evidence_expired")
    return [dict(row) for row in rows]


def batches_with_channel_language(
    connection: Connection,
    raw: list[dict[str, Any]],
    requested_language: str,
    now: datetime,
) -> list[tuple[dict[str, Any], Batch]]:
    """Attach a retained channel content-language claim without changing provider payloads."""
    parsed = [(observation, Batch.model_validate(observation["payload"])) for observation in raw]
    claims = {
        (canonical_platform(batch.provenance.provider), channel.id): requested_language
        for _, batch in parsed
        for channel in batch.channels
        if requested_language in channel.content_languages
    }
    video_channels = {
        (canonical_platform(batch.provenance.provider), video.channel_id)
        for _, batch in parsed
        for video in batch.videos
        if video.language is None
    }
    if video_channels:
        rows = connection.execute(
            select(
                s.channels.c.platform,
                s.channels.c.external_id,
                s.channel_observations.c.data,
            )
            .join(s.channel_observations, s.channel_observations.c.channel_id == s.channels.c.id)
            .where(
                s.channel_observations.c.retain_until > now,
                s.channels.c.platform.in_({provider for provider, _ in video_channels}),
                s.channels.c.external_id.in_({channel for _, channel in video_channels}),
            )
            .order_by(
                s.channels.c.platform,
                s.channels.c.external_id,
                s.channel_observations.c.observed_at.desc(),
            )
        ).mappings()
        for row in rows:
            key = (row["platform"], row["external_id"])
            if key in video_channels and requested_language in row["data"].get(
                "content_languages", []
            ):
                claims.setdefault(key, requested_language)
    result = []
    for observation, batch in parsed:
        videos = tuple(
            video.model_copy(
                update={
                    "language": claims[
                        (canonical_platform(batch.provenance.provider), video.channel_id)
                    ],
                    "language_evidence": (
                        "provider channel content-language claim; video audio unverified"
                    ),
                }
            )
            if video.language is None
            and (canonical_platform(batch.provenance.provider), video.channel_id) in claims
            else video
            for video in batch.videos
        )
        result.append((observation, batch.model_copy(update={"videos": videos})))
    return result


def merge_youtube_video(primary: Video, supplemental: Video) -> Video:
    """Use canonical YouTube fields without replacing vidIQ-only classifications."""
    if primary.id != supplemental.id or primary.channel_id != supplemental.channel_id:
        return primary
    return primary.model_copy(
        update={
            "title": supplemental.title or primary.title,
            "description": supplemental.description
            if supplemental.description is not None
            else primary.description,
            "published_at": supplemental.published_at or primary.published_at,
            "views": supplemental.views if supplemental.views is not None else primary.views,
            "language": supplemental.language or primary.language,
            "language_evidence": supplemental.language_evidence or primary.language_evidence,
            "category": primary.category or supplemental.category,
            "duration_seconds": supplemental.duration_seconds
            if supplemental.duration_seconds is not None
            else primary.duration_seconds,
        }
    )


class Pipeline:
    def __init__(
        self,
        engine: Engine,
        *,
        clock: Callable[[], datetime] = utcnow,
        provider: Provider | None = None,
        maximum_calls: int = 20,
        settings: Settings | None = None,
        embedder: Embedder | None = None,
        youtube: Provider | None = None,
    ):
        self.engine = engine
        self.clock = clock
        self.provider: Provider = provider or SyntheticProvider()
        self._provider_override = provider is not None
        if not 1 <= maximum_calls <= 100:
            raise ValueError("bounded query batch required")
        self.maximum_calls = maximum_calls
        self.settings = settings or Settings()
        self.embedder = embedder
        self.youtube: Provider | None = youtube
        self._youtube_override = youtube is not None

    async def process(self, job_id: UUID, owner: str) -> None:
        try:
            while True:
                now = self.clock()
                with self.engine.begin() as connection:
                    job = owned_job(connection, job_id, owner, now)
                    run = (
                        connection.execute(
                            select(s.analysis_runs).where(s.analysis_runs.c.id == job["run_id"])
                        )
                        .mappings()
                        .one()
                    )
                    profile_row = (
                        connection.execute(
                            select(s.creator_profiles).where(
                                s.creator_profiles.c.id == run["profile_id"]
                            )
                        )
                        .mappings()
                        .one()
                    )
                    profile = CreatorProfile.model_validate(profile_row["configuration"])
                    self._ensure_provider(
                        connection,
                        run["mode"],
                        run["trigger"] == "scheduled",
                        now,
                    )
                    stage = job["stage"]
                    checkpoints = job["checkpoints"]
                    if stage == "planning":
                        plan = plan_family(
                            connection, run["profile_id"], run["id"], now, profile.exploration_share
                        )
                        confirm_stage(connection, job_id, owner, now, stage, plan)
                        continue
                if stage == "query":
                    await self.query(
                        job,
                        run["profile_id"],
                        profile,
                        owner,
                        scheduled=run["trigger"] == "scheduled",
                    )
                    continue
                if stage == "enrichment":
                    await self.enrich_youtube(
                        job,
                        run["profile_id"],
                        profile,
                        owner,
                        live=run["mode"] == "live",
                        scheduled=run["trigger"] == "scheduled",
                    )
                    continue
                if stage == "backlog":
                    for evaluation_key in checkpoints["evaluation"]["evaluation_ids"]:
                        with self.engine.begin() as connection:
                            heartbeat(connection, job_id, owner, self.clock())
                        await enrich(self.engine, UUID(evaluation_key), self.settings, self.clock)
                with self.engine.begin() as connection:
                    owned_job(connection, job_id, owner, self.clock())
                    evidence = checkpoints.get("enrichment", checkpoints["query"])
                    raw = observations(connection, evidence["raw_ids"], now)
                    if stage == "normalization":
                        self.normalize(connection, raw, profile.language, now)
                        result: dict[str, Any] = {"raw_ids": evidence["raw_ids"]}
                    elif stage == "cohort":
                        result = self.cohorts(
                            connection, raw, job["run_id"], checkpoints["planning"], profile, now
                        )
                    elif stage == "metrics":
                        result = self.metrics(
                            connection, checkpoints["cohort"]["cohort_ids"], job["run_id"], now
                        )
                    elif stage == "evaluation":
                        for evaluation_key in checkpoints["metrics"]["evaluation_ids"]:
                            evaluation = (
                                connection.execute(
                                    select(s.evaluation_versions).where(
                                        s.evaluation_versions.c.id == UUID(evaluation_key)
                                    )
                                )
                                .mappings()
                                .one()
                            )
                            ensure_default_recipe(
                                connection, evaluation["opportunity_id"], run["profile_id"], now
                            )
                            saved = latest_plan(
                                connection, evaluation["opportunity_id"], run["profile_id"]
                            )
                            if (
                                evaluation["expired_at"] is not None
                                or evaluation["retain_until"] <= self.clock()
                            ):
                                continue
                            assessment = None
                            if saved:
                                assessment = evaluate_plan(
                                    ProductionPlan.model_validate(saved["configuration"]), profile
                                )
                                assessment["assignment_version"] = saved["version"]
                                assessment["profile_version"] = profile_row["version"]
                            combined = combine(
                                MarketEvaluation.model_validate(
                                    evaluation["explanation"]["market"]
                                ),
                                assessment,
                            )
                            snapshot = evaluation["explanation"] | {
                                "production": assessment,
                                "creator_fit": assessment["status"] if assessment else "incomplete",
                                "combined": combined.model_dump(mode="json"),
                            }
                            evidence_ids = tuple(
                                str(value)
                                for value in connection.execute(
                                    select(s.evidence_links.c.observation_id).where(
                                        s.evidence_links.c.evaluation_id == evaluation["id"],
                                        s.evidence_links.c.observation_id.is_not(None),
                                    )
                                ).scalars()
                            )
                            snapshot["narrative"] = snapshot_explanation(
                                snapshot, str(evaluation["id"]), evidence_ids
                            ).model_dump(mode="json")
                            connection.execute(
                                update(s.evaluation_versions)
                                .where(s.evaluation_versions.c.id == evaluation["id"])
                                .values(
                                    creator_fit=float(assessment["score"])
                                    if assessment and assessment["score"] is not None
                                    else None,
                                    final_score=combined.score,
                                    confidence=combined.confidence,
                                    state=combined.state,
                                    explanation=snapshot,
                                )
                            )
                        result = {
                            "evaluation_ids": checkpoints["metrics"]["evaluation_ids"],
                            "creator_fit": "default_recipe_auto_applied_unless_manually_assigned",
                        }
                    elif stage == "backlog":
                        result = {"evaluation_ids": checkpoints["metrics"]["evaluation_ids"]}
                        result["ranking_snapshot_id"] = str(
                            capture(connection, job["run_id"], self.clock())
                        )
                        enrichment_complete = (
                            checkpoints.get("enrichment", {}).get("status") != "partial"
                        )
                        complete = (
                            checkpoints["query"].get("complete", True) and enrichment_complete
                        )
                        missing_refresh = (
                            checkpoints["planning"]["kind"] == "refresh"
                            and not result["evaluation_ids"]
                        )
                        if missing_refresh:
                            complete = False
                        finish_work(connection, checkpoints["planning"], now, complete)
                        connection.execute(
                            update(s.analysis_runs)
                            .where(s.analysis_runs.c.id == job["run_id"])
                            .values(
                                coverage={
                                    "synthetic": run["mode"] == "synthetic",
                                    "evaluated_cohorts": len(checkpoints["cohort"]["cohort_ids"]),
                                    "catalog_pending": checkpoints["planning"]["catalog_pending"],
                                    "refresh_pending": checkpoints["planning"]["refresh_pending"],
                                    "work_kind": checkpoints["planning"]["kind"],
                                    "grouping": checkpoints["cohort"].get("grouping", {}),
                                    "complete": complete,
                                    "pending_reason": (
                                        "refresh_evidence_insufficient"
                                        if missing_refresh
                                        else checkpoints.get("enrichment", {}).get("reason")
                                        or checkpoints["query"].get("reason")
                                    ),
                                }
                            )
                        )
                    else:
                        raise ProviderError("unknown_pipeline_stage")
                    confirm_stage(
                        connection,
                        job_id,
                        owner,
                        self.clock(),
                        stage,
                        result,
                        partial=not complete if stage == "backlog" else False,
                    )
                    if stage == "backlog":
                        return
        except ProviderError as error:
            if error.code == "lease_lost":
                return
            with self.engine.begin() as connection:
                try:
                    fail_job(
                        connection,
                        job_id,
                        owner,
                        self.clock(),
                        error,
                        maximum_attempts=self.settings.worker_maximum_attempts,
                    )
                except ProviderError as ownership_error:
                    if ownership_error.code != "lease_lost":
                        raise

    def _ensure_provider(
        self, connection: Connection, mode: str, scheduled: bool, now: datetime
    ) -> None:
        if mode == "synthetic":
            # Explicit provider injection is used by deterministic fault tests. The
            # production worker never injects a provider and must stay synthetic here.
            if not self._provider_override and self.provider.name != "synthetic":
                raise ProviderError("provider_mode_mismatch", not_sent=True)
            return
        if mode != "live":
            raise ProviderError("unsupported_runtime_mode", not_sent=True)
        report = preflight(connection, self.settings, now, scheduled=scheduled)
        if not report["ready"]:
            raise ProviderError("live_prerequisites_incomplete", not_sent=True)
        if not self._provider_override:
            self.provider = vidiq_provider(self.settings)
        if self.provider.name != "vidiq":
            raise ProviderError("provider_mode_mismatch", not_sent=True)

    async def query(
        self,
        job: dict[str, Any],
        profile_id: UUID,
        profile: CreatorProfile,
        owner: str,
        *,
        scheduled: bool = False,
    ) -> None:
        synthetic = self.provider.name == "synthetic"
        auth_scope = "synthetic" if synthetic else self.settings.vidiq_auth_scope
        if auth_scope is None:
            raise ProviderError("account_scope_required", not_sent=True)
        gateway = Gateway(
            self.engine,
            self.provider,
            profile_id,
            job["run_id"],
            auth_scope,
            profile,
            {} if synthetic else vidiq_limits(profile),
            {} if synthetic else vidiq_tariffs(),
            scheduled=scheduled,
            maximum_calls=self.maximum_calls,
            credit_cycle_started_at=None
            if synthetic
            else self.settings.vidiq_credit_cycle_started_at,
        )
        await collect(self.engine, gateway, job, owner, profile, self.clock, self.maximum_calls)

    async def enrich_youtube(
        self,
        job: dict[str, Any],
        profile_id: UUID,
        profile: CreatorProfile,
        owner: str,
        *,
        live: bool,
        scheduled: bool,
    ) -> None:
        query_ids = job["checkpoints"]["query"]["raw_ids"]
        if not live or not self.settings.youtube_live_enabled:
            with self.engine.begin() as connection:
                confirm_stage(
                    connection,
                    job["id"],
                    owner,
                    self.clock(),
                    "enrichment",
                    {
                        "raw_ids": query_ids,
                        "provider": "youtube",
                        "status": "disabled",
                        "requested_videos": 0,
                    },
                )
            return
        with self.engine.connect() as connection:
            raw = observations(connection, query_ids, self.clock())
        video_ids = sorted(
            {
                video.id
                for observation in raw
                for batch in (Batch.model_validate(observation["payload"]),)
                if batch.provenance.provider == "vidiq"
                for video in batch.videos
            }
        )[: self.settings.youtube_maximum_videos]
        if not video_ids:
            with self.engine.begin() as connection:
                confirm_stage(
                    connection,
                    job["id"],
                    owner,
                    self.clock(),
                    "enrichment",
                    {
                        "raw_ids": query_ids,
                        "provider": "youtube",
                        "status": "no_candidates",
                        "requested_videos": 0,
                    },
                )
            return
        if not self._youtube_override:
            self.youtube = youtube_provider(self.settings)
        if self.youtube is None or self.youtube.name != "youtube":
            raise ProviderError("provider_mode_mismatch", not_sent=True)
        auth_scope = self.settings.youtube_auth_scope
        if auth_scope is None:
            raise ProviderError("account_scope_required", not_sent=True)
        gateway = Gateway(
            self.engine,
            self.youtube,
            profile_id,
            job["run_id"],
            auth_scope,
            profile,
            youtube_limits(self.settings),
            youtube_tariffs(),
            scheduled=scheduled,
            maximum_calls=self.maximum_calls,
        )
        scope = hashlib.sha256(json.dumps(video_ids).encode()).hexdigest()
        saved = job["checkpoints"]
        receipts = (
            dict(saved.get("youtube_receipts_v1", {}))
            if saved.get("youtube_scope_v1") == scope
            else {}
        )
        complete, reason = True, None
        try:
            for index in range(0, len(video_ids), 50):
                chunk = video_ids[index : index + 50]
                key = f"videos:{index // 50}"
                with self.engine.begin() as connection:
                    heartbeat(connection, job["id"], owner, self.clock())
                    if key in receipts:
                        retained = connection.execute(
                            select(s.raw_observations.c.id).where(
                                s.raw_observations.c.id == UUID(receipts[key]),
                                s.raw_observations.c.retain_until > self.clock(),
                            )
                        ).scalar_one_or_none()
                        if retained is not None:
                            continue
                        del receipts[key]
                _, raw_id, _ = await gateway.fetch(
                    Operation.VIDEOS,
                    {"id": ",".join(chunk)},
                    self.clock(),
                )
                receipts[key] = str(raw_id)
                with self.engine.begin() as connection:
                    current = owned_job(connection, job["id"], owner, self.clock())
                    connection.execute(
                        update(s.jobs)
                        .where(s.jobs.c.id == job["id"])
                        .values(
                            checkpoints=current["checkpoints"]
                            | {
                                "youtube_receipts_v1": receipts,
                                "youtube_scope_v1": scope,
                            }
                        )
                    )
        except ProviderError as error:
            if error.code not in {
                "batch_limit",
                "run_budget_exhausted",
                "period_budget_exhausted",
                "shared_budget_exhausted",
            }:
                raise
            complete, reason = False, error.code
        with self.engine.begin() as connection:
            current = owned_job(connection, job["id"], owner, self.clock())
            retained = {
                str(value)
                for value in connection.execute(
                    select(s.raw_observations.c.id).where(
                        s.raw_observations.c.id.in_([UUID(value) for value in receipts.values()]),
                        s.raw_observations.c.retain_until > self.clock(),
                    )
                ).scalars()
            }
            receipts = {key: value for key, value in receipts.items() if value in retained}
            connection.execute(
                update(s.jobs)
                .where(s.jobs.c.id == job["id"])
                .values(
                    checkpoints=current["checkpoints"]
                    | {"youtube_receipts_v1": receipts, "youtube_scope_v1": scope}
                )
            )
            confirm_stage(
                connection,
                job["id"],
                owner,
                self.clock(),
                "enrichment",
                {
                    "raw_ids": sorted(set(query_ids) | set(receipts.values())),
                    "provider": "youtube",
                    "status": "complete" if complete else "partial",
                    "requested_videos": len(video_ids),
                    "batches": len(receipts),
                    "reason": reason,
                },
            )

    @staticmethod
    def normalize(
        connection: Connection,
        raw: list[dict[str, Any]],
        requested_language: str,
        now: datetime,
    ) -> None:
        for observation, batch in batches_with_channel_language(
            connection, raw, requested_language, now
        ):
            for channel in batch.channels:
                channel_id = channel_identity(connection, batch.provenance.provider, channel.id)
                connection.execute(
                    insert(s.channel_observations)
                    .values(
                        channel_id=channel_id,
                        raw_observation_id=observation["id"],
                        subscribers=channel.subscribers,
                        country=channel.country,
                        observed_at=batch.provenance.observed_at or batch.provenance.fetched_at,
                        retain_until=observation["retain_until"],
                        data=channel.model_dump(mode="json"),
                    )
                    .on_conflict_do_nothing(index_elements=["channel_id", "raw_observation_id"])
                )
            for video in batch.videos:
                channel_id = channel_identity(
                    connection, batch.provenance.provider, video.channel_id
                )
                video_id = video_identity(
                    connection, batch.provenance.provider, video.id, channel_id
                )
                connection.execute(
                    insert(s.video_observations)
                    .values(
                        video_id=video_id,
                        raw_observation_id=observation["id"],
                        format=video.format.value,
                        language=video.language,
                        views=video.views,
                        published_at=video.published_at,
                        observed_at=batch.provenance.observed_at or batch.provenance.fetched_at,
                        retain_until=observation["retain_until"],
                        data=video.model_dump(mode="json"),
                    )
                    .on_conflict_do_nothing(index_elements=["video_id", "raw_observation_id"])
                )

    def cohorts(
        self,
        connection: Connection,
        raw: list[dict[str, Any]],
        run_id: UUID,
        plan: dict[str, Any],
        profile: CreatorProfile,
        now: datetime,
    ) -> dict[str, Any]:
        if not raw:
            return {"cohort_ids": []}
        video_sources: dict[str, tuple[Video, UUID, str, set[UUID]]] = {}
        youtube_sources: dict[str, tuple[Video, UUID]] = {}
        enriched = batches_with_channel_language(connection, raw, profile.language, now)
        for observation, batch in sorted(
            enriched,
            key=lambda row: (
                row[1].provenance.operation == Operation.CHANNEL_VIDEOS,
                row[0]["fetched_at"],
                str(row[0]["id"]),
            ),
        ):
            if (
                batch.provenance.provider == "youtube"
                and batch.provenance.operation == Operation.VIDEOS
            ):
                for video in batch.videos:
                    youtube_sources[video.id] = (video, observation["id"])
                continue
            method = (
                "recent" if batch.provenance.operation == Operation.CHANNEL_VIDEOS else "outliers"
            )
            for video in batch.videos:
                video_sources[video.id] = (video, observation["id"], method, {observation["id"]})
        for video_id, (supplemental, raw_id) in youtube_sources.items():
            if video_id not in video_sources:
                continue
            primary, primary_raw_id, method, source_ids = video_sources[video_id]
            video_sources[video_id] = (
                merge_youtube_video(primary, supplemental),
                primary_raw_id,
                method,
                source_ids | {raw_id},
            )
        videos = tuple(entry[0] for entry in video_sources.values())
        terms = selection_terms(plan["family_key"], plan["query"])
        embedder, fallback_reason = (
            (self.embedder, None)
            if self.embedder is not None
            else configured_embedder(self.settings)
        )
        semantic_ids: set[str] = set()
        semantic_scores: dict[str, float] = {}
        if embedder is not None:
            try:
                semantic_ids, semantic_scores = semantic_relevance(
                    videos,
                    query=plan["query"],
                    embedder=embedder,
                    threshold=self.settings.topic_relevance_threshold,
                    maximum_text_chars=self.settings.topic_maximum_text_chars,
                )
            except (ValueError, RuntimeError, OSError, ImportError):
                embedder, fallback_reason = None, "embedding_failed"
        scope = grouping_scope(connection, run_id, profile.language)
        eligible_ids = {
            member.video.id
            for format in profile.formats
            for member in sample(
                videos,
                now=now,
                format=format,
                language=profile.language,
                terms=terms,
                selection_method="recent",
                small_threshold=profile.small_channel_subscribers,
                semantic_matches=frozenset(semantic_ids),
            )
            if member.included
        }
        groups, grouping_metadata = prepare_groups(
            connection,
            videos,
            UUID(plan["family_id"]),
            scope,
            self.settings,
            embedder,
            fallback_reason,
            now,
            eligible_ids=eligible_ids,
        )
        cohort_ids = []
        deadline = min(observation["retain_until"] for observation in raw)
        target_key = None
        if plan.get("target_topic_id"):
            target_key = connection.execute(
                select(s.topics.c.identity_key).where(
                    s.topics.c.id == UUID(plan["target_topic_id"])
                )
            ).scalar_one()
        for group in groups:
            key = scoped_key(plan["family_id"], group, scope)
            connection.execute(
                insert(s.topics)
                .values(
                    family_id=UUID(plan["family_id"]),
                    identity_key=key,
                    label=group.label,
                    method_version=group.method,
                    retain_until=deadline,
                )
                .on_conflict_do_update(
                    index_elements=["identity_key"],
                    set_={
                        "label": group.label,
                        "method_version": group.method,
                        "retain_until": deadline,
                    },
                )
            )
            topic_id: UUID = connection.execute(
                select(s.topics.c.id).where(s.topics.c.identity_key == key)
            ).scalar_one()
            group_raw_ids = {
                raw_id for video_id in group.member_ids for raw_id in video_sources[video_id][3]
            }
            artifact_id = store_group(
                connection,
                topic_id,
                run_id,
                group,
                grouping_metadata,
                {row["id"]: row["retain_until"] for row in raw if row["id"] in group_raw_ids},
                now,
            )
            # Preserve ambiguous correspondence evidence, but only update the
            # requested opportunity when its identity was matched unambiguously.
            if target_key is not None and key != target_key:
                continue
            for format in profile.formats:
                if plan.get("target_format") and format.value != plan["target_format"]:
                    continue
                selected = tuple(
                    video
                    for video in videos
                    if video.id in group.member_ids
                    and video.format in {format, VideoFormat.UNKNOWN}
                )
                members = sample(
                    selected,
                    now=now,
                    format=format,
                    language=profile.language,
                    terms=terms,
                    selection_method="recent",
                    small_threshold=profile.small_channel_subscribers,
                    semantic_matches=frozenset(semantic_ids),
                )
                members = tuple(
                    member.model_copy(
                        update={"selection_method": video_sources[member.video.id][2]}
                    )
                    for member in members
                )
                cohort_id = insert_record(
                    connection,
                    "cohorts",
                    {
                        "run_id": run_id,
                        "topic_id": topic_id,
                        "format": format.value,
                        "language": profile.language,
                        "criteria": {
                            "method": group.method,
                            "opportunity_id": plan.get("opportunity_id"),
                            "topic_artifact_id": str(artifact_id),
                            "topic_status": "ambiguous"
                            if group.ambiguous_matches
                            else group.method,
                            "topic_fallback_reason": grouping_metadata["fallback_reason"],
                            "topic_omitted_videos": grouping_metadata["omitted"],
                            "semantic_relevance": {
                                "model_version": embedder.version if embedder else None,
                                "threshold": self.settings.topic_relevance_threshold,
                                "confirmed": sum(
                                    video_id in semantic_ids for video_id in group.member_ids
                                ),
                                "evaluated": sum(
                                    video_id in semantic_scores for video_id in group.member_ids
                                ),
                                "fallback_reason": fallback_reason,
                            },
                            "youtube_enrichment_raw_ids": sorted(
                                {
                                    str(raw_id)
                                    for video_id in group.member_ids
                                    for raw_id in video_sources[video_id][3]
                                    if raw_id != video_sources[video_id][1]
                                }
                            ),
                            "age_window_days": 90,
                            "small_threshold": profile.small_channel_subscribers,
                        },
                        "coverage": {
                            "received": len(members),
                            "included": sum(member.included for member in members),
                        },
                    },
                )
                for member in members:
                    row = connection.execute(
                        select(
                            s.video_observations.c.id,
                            s.video_observations.c.video_id,
                            s.video_observations.c.raw_observation_id,
                        )
                        .join(s.videos, s.videos.c.id == s.video_observations.c.video_id)
                        .where(
                            s.videos.c.external_id == member.video.id,
                            s.video_observations.c.raw_observation_id
                            == video_sources[member.video.id][1],
                        )
                        .order_by(s.video_observations.c.observed_at.desc())
                        .limit(1)
                    ).one()
                    connection.execute(
                        insert(s.cohort_memberships).values(
                            cohort_id=cohort_id,
                            video_id=row.video_id,
                            video_observation_id=row.id,
                            included=member.included,
                            reason_code=member.reason,
                            selection_method=member.selection_method,
                            size_stratum=member.size_stratum,
                            age_band=member.age_band,
                        )
                    )
                    if not member.included:
                        continue
                    connection.execute(
                        insert(s.topic_memberships)
                        .values(
                            topic_id=topic_id,
                            video_id=row.video_id,
                            observation_id=row.raw_observation_id,
                        )
                        .on_conflict_do_update(
                            index_elements=["topic_id", "video_id"],
                            set_={"observation_id": row.raw_observation_id},
                        )
                    )
                cohort_ids.append(str(cohort_id))
        return {
            "cohort_ids": cohort_ids,
            "grouping": {
                "fallback_reason": grouping_metadata["fallback_reason"],
                "received": grouping_metadata["received"],
                "processed": grouping_metadata["processed"],
                "omitted": grouping_metadata["omitted"],
                "ambiguous_groups": sum(bool(group.ambiguous_matches) for group in groups),
                "noise_groups": sum(group.method == "noise" for group in groups),
            },
        }

    def metrics(
        self, connection: Connection, cohort_ids: list[str], run_id: UUID, now: datetime
    ) -> dict[str, Any]:
        from nicheradar.discovery.sampling import Membership

        evaluation_ids = []
        for cohort_key in cohort_ids:
            cohort_id = UUID(cohort_key)
            cohort = (
                connection.execute(select(s.cohorts).where(s.cohorts.c.id == cohort_id))
                .mappings()
                .one()
            )
            rows = [
                dict(row)
                for row in (
                    connection.execute(
                        select(
                            s.cohort_memberships,
                            s.video_observations.c.data,
                            s.video_observations.c.retain_until,
                            s.video_observations.c.raw_observation_id,
                        )
                        .join(
                            s.video_observations,
                            s.video_observations.c.id
                            == s.cohort_memberships.c.video_observation_id,
                        )
                        .where(s.cohort_memberships.c.cohort_id == cohort_id)
                    )
                    .mappings()
                    .all()
                )
            ]
            if not rows:
                continue
            metric_enrichment_sources: dict[UUID, datetime] = {}
            enrichment_ids = [
                UUID(value) for value in cohort["criteria"].get("youtube_enrichment_raw_ids", [])
            ]
            if enrichment_ids:
                supplemental_rows = (
                    connection.execute(
                        select(
                            s.video_observations.c.video_id,
                            s.video_observations.c.data,
                            s.video_observations.c.raw_observation_id,
                            s.video_observations.c.retain_until,
                            s.video_observations.c.observed_at,
                        )
                        .where(
                            s.video_observations.c.raw_observation_id.in_(enrichment_ids),
                            s.video_observations.c.retain_until > now,
                        )
                        .order_by(s.video_observations.c.observed_at.desc())
                    )
                    .mappings()
                    .all()
                )
                supplemental_by_video: dict[UUID, dict[str, Any]] = {}
                for supplemental_record in supplemental_rows:
                    supplemental_by_video.setdefault(
                        supplemental_record["video_id"], dict(supplemental_record)
                    )
                for row in rows:
                    supplemental_row = supplemental_by_video.get(row["video_id"])
                    if supplemental_row is None:
                        continue
                    row["data"] = merge_youtube_video(
                        Video.model_validate(row["data"]),
                        Video.model_validate(supplemental_row["data"]),
                    ).model_dump(mode="json")
                    row["retain_until"] = min(row["retain_until"], supplemental_row["retain_until"])
                    metric_enrichment_sources[supplemental_row["raw_observation_id"]] = (
                        supplemental_row["retain_until"]
                    )
            members = tuple(
                Membership.model_validate(
                    {
                        "video": row["data"],
                        "included": row["included"],
                        "reason": row["reason_code"],
                        "size_stratum": row["size_stratum"],
                        "age_band": row["age_band"],
                        "selection_method": row["selection_method"],
                    }
                )
                for row in rows
            )
            metrics = calculate(members, now)
            temporal, temporal_sources = temporal_evidence(connection, rows, now, self.settings)
            metrics = metrics.model_copy(
                update={"trend_relative_change": temporal["trend_relative_change"]}
            )
            topic_status = cohort["criteria"].get("topic_status")
            opportunity = (
                UUID(cohort["criteria"]["opportunity_id"])
                if cohort["criteria"].get("opportunity_id")
                else opportunity_identity(
                    connection,
                    cohort["topic_id"],
                    "english-content-viewers",
                    cohort["language"],
                    VideoFormat(cohort["format"]),
                )
            )
            run = (
                connection.execute(select(s.analysis_runs).where(s.analysis_runs.c.id == run_id))
                .mappings()
                .one()
            )
            opportunity_row = (
                connection.execute(
                    select(s.opportunities).where(s.opportunities.c.id == opportunity)
                )
                .mappings()
                .one()
            )
            saved_config = latest_configuration(connection, opportunity, run["profile_id"])
            scoring_config = (
                ScoringConfiguration.model_validate(saved_config["configuration"])
                if saved_config
                and saved_config["configuration"]
                and saved_config["retain_until"] > now
                else None
            )
            advertising = assess_advertising(
                scoring_config.advertising if scoring_config else None,
                format=VideoFormat(cohort["format"]),
                language=cohort["language"],
                audience_key=opportunity_row["audience_key"],
                synthetic=run["mode"] == "synthetic",
                now=now,
            )
            market = evaluate_market(
                metrics,
                VideoFormat(cohort["format"]),
                scoring_config.references if scoring_config else None,
                synthetic=run["mode"] == "synthetic",
                advertising=advertising,
                relevance_reviewed=bool(scoring_config and scoring_config.relevance_review),
            )
            if topic_status in {"noise", "unclassified", "ambiguous"}:
                market = market.model_copy(
                    update={
                        "state": "insufficient_evidence",
                        "confidence": "insufficient",
                        "score": None,
                    }
                )
            deadline = min(row["retain_until"] for row in rows)
            if scoring_config:
                deadline = min(deadline, scoring_config.retain_until)
            evidence_ids = {row["raw_observation_id"] for row in rows}
            evidence_ids.update(metric_enrichment_sources)
            if temporal_sources:
                deadline = min(deadline, *temporal_sources.values())
                evidence_ids.update(temporal_sources)
            if cohort["criteria"].get("topic_artifact_id"):
                artifact_id = UUID(cohort["criteria"]["topic_artifact_id"])
                artifact = (
                    connection.execute(
                        select(s.topic_artifacts).where(
                            s.topic_artifacts.c.id == artifact_id,
                            s.topic_artifacts.c.retain_until > now,
                        )
                    )
                    .mappings()
                    .first()
                )
                if artifact is None:
                    raise ProviderError("evidence_expired")
                sources = connection.execute(
                    select(s.raw_observations.c.id, s.raw_observations.c.retain_until)
                    .join(
                        topic_artifact_sources,
                        topic_artifact_sources.c.observation_id == s.raw_observations.c.id,
                    )
                    .where(topic_artifact_sources.c.artifact_id == artifact_id)
                ).all()
                if any(source.retain_until <= now for source in sources):
                    raise ProviderError("evidence_expired")
                evidence_ids.update(source.id for source in sources)
                deadline = min(
                    deadline, artifact["retain_until"], *(source.retain_until for source in sources)
                )
            evaluation_id = append_evaluation(
                connection,
                opportunity,
                {
                    "cohort_id": cohort_id,
                    "run_id": run_id,
                    "method_version": "opportunity-v2",
                    "reference_version": market.reference_version,
                    "state": market.state,
                    "confidence": market.confidence,
                    "market_score": market.score,
                    "explanation": {
                        "market": market.model_dump(mode="json"),
                        "advertising": advertising.model_dump(mode="json"),
                        "scoring_configuration": scoring_config.model_dump(mode="json")
                        if scoring_config
                        else None,
                        "scoring_configuration_version": saved_config["version"]
                        if saved_config
                        else None,
                        "metrics": metrics.model_dump(mode="json"),
                        "method_context": {
                            "grouping": cohort["criteria"].get("method"),
                            "age_window_days": cohort["criteria"].get("age_window_days"),
                            "small_threshold": cohort["criteria"].get("small_threshold"),
                            "trend_interval_tolerance": self.settings.trend_interval_tolerance,
                            "trend_lookback_days": self.settings.trend_lookback_days,
                            "embedding_model_version": self.settings.embedding_model_version,
                            "topic_minimum_size": self.settings.topic_minimum_size,
                            "topic_similarity_threshold": self.settings.topic_similarity_threshold,
                        },
                        "temporal": temporal,
                        "synthetic": run["mode"] == "synthetic",
                        "creator_fit": "No production recipe has been evaluated.",
                        "topic": {
                            "status": topic_status,
                            "fallback_reason": cohort["criteria"].get("topic_fallback_reason"),
                            "omitted_videos": cohort["criteria"].get("topic_omitted_videos", 0),
                        },
                    },
                    "retain_until": deadline,
                    "created_at": now,
                },
            )
            for raw_id in evidence_ids:
                insert_record(
                    connection,
                    "evidence_links",
                    {
                        "evaluation_id": evaluation_id,
                        "observation_id": raw_id,
                        "availability": "available",
                        "claim_key": "market_metrics_and_temporal_history"
                        if raw_id in temporal_sources
                        else "market_metrics",
                        "retain_until": deadline,
                    },
                )
            for name, value in market.components.items():
                insert_record(
                    connection,
                    "feature_values",
                    {
                        "evaluation_id": evaluation_id,
                        "name": name,
                        "value": value,
                        "unit": "score_0_100",
                        "definition": {"method_version": market.method_version},
                        "retain_until": deadline,
                    },
                )
            evaluation_ids.append(str(evaluation_id))
        return {"evaluation_ids": evaluation_ids}
