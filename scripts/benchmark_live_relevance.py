"""Score retained live evidence and emit aggregates without external text or identifiers."""

import hashlib
import json
import os
import resource
import sys
import time
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import select

from nicheradar.config import Settings
from nicheradar.discovery.sampling import relevance, selection_terms
from nicheradar.domain.profile import CreatorProfile
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.database import database_engine
from nicheradar.topics.grouping import semantic_relevance
from nicheradar.topics.runtime import configured_embedder
from nicheradar.workers.pipeline import batches_with_channel_language, observations

os.environ.update(json.load(sys.stdin))
settings = Settings()
engine = database_engine(settings)
with engine.connect() as connection:
    job = (
        connection.execute(
            select(s.jobs, s.analysis_runs.c.profile_id)
            .join(s.analysis_runs, s.analysis_runs.c.id == s.jobs.c.run_id)
            .where(s.analysis_runs.c.mode == "live", s.analysis_runs.c.trigger == "scheduled")
            .order_by(s.jobs.c.created_at.desc(), s.jobs.c.id)
            .limit(1)
        )
        .mappings()
        .one()
    )
    profile = CreatorProfile.model_validate(
        connection.execute(
            select(s.creator_profiles.c.configuration).where(
                s.creator_profiles.c.id == job["profile_id"]
            )
        ).scalar_one()
    )
    raw = observations(connection, job["checkpoints"]["query"]["raw_ids"], datetime.now(UTC))
    batches = batches_with_channel_language(connection, raw, profile.language, datetime.now(UTC))

videos = {video.id: video for _, batch in batches for video in batch.videos}
plan = job["checkpoints"]["planning"]
terms = selection_terms(plan["family_key"], plan["query"])
embedder, fallback_reason = configured_embedder(settings)
if embedder is None:
    raise SystemExit(fallback_reason or "model unavailable")
started = time.monotonic()
_, scores = semantic_relevance(
    tuple(videos.values()),
    query=plan["query"],
    embedder=embedder,
    threshold=settings.topic_relevance_threshold,
    maximum_text_chars=settings.topic_maximum_text_chars,
)
elapsed = time.monotonic() - started
ordered = sorted(scores.values())


def percentile(fraction: float) -> float | None:
    if not ordered:
        return None
    return round(ordered[round((len(ordered) - 1) * fraction)], 4)


lexical = {video_id: relevance(video, terms) for video_id, video in videos.items()}
thresholds = (0.35, 0.4, 0.45, 0.5, 0.55, 0.6)
print(
    json.dumps(
        {
            "model_version": embedder.version,
            "job_id": str(job["id"]),
            "query_sha256": hashlib.sha256(plan["query"].encode()).hexdigest(),
            "videos": len(videos),
            "lexical": dict(Counter(lexical.values())),
            "language_confirmed": sum(
                video.language == profile.language for video in videos.values()
            ),
            "encode_seconds": round(elapsed, 3),
            "process_peak_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
            "score_percentiles": {
                "minimum": percentile(0),
                "p10": percentile(0.1),
                "p25": percentile(0.25),
                "median": percentile(0.5),
                "p75": percentile(0.75),
                "p90": percentile(0.9),
                "maximum": percentile(1),
            },
            "confirmed_by_threshold": {
                str(threshold): {
                    "all": sum(score >= threshold for score in scores.values()),
                    "lexically_unknown": sum(
                        score >= threshold and lexical[video_id] == "unknown"
                        for video_id, score in scores.items()
                    ),
                    "long": sum(
                        score >= threshold and videos[video_id].format.value == "long"
                        for video_id, score in scores.items()
                    ),
                    "shorts": sum(
                        score >= threshold and videos[video_id].format.value == "shorts"
                        for video_id, score in scores.items()
                    ),
                }
                for threshold in thresholds
            },
        }
    )
)
