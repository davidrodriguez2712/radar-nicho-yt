"""Stage sequence for the channel-analysis flow; parallel to workers/queue.py's
STAGES/confirm_stage(), which are hardcoded to the catalog discovery sequence and cannot
be reused for a different stage sequence without risking index/completion-detection bugs.

confirm_channel_analysis_stage() mirrors confirm_stage()'s checkpoint-merge and
status-transition behavior exactly; the only difference is which stage tuple drives
"next stage"/"final stage" detection.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, update

from nicheradar.integrations.contracts import ProviderError
from nicheradar.repositories import schema_v1 as s
from nicheradar.workers.queue import owned_job

CHANNEL_ANALYSIS_STAGES = (
    "resolve",
    "target_videos",
    "discover_comparables",
    "comparable_videos",
    "metrics",
    "profit",
    "persist",
)


def confirm_channel_analysis_stage(
    connection: Connection,
    job_id: UUID,
    owner: str,
    now: datetime,
    stage: str,
    checkpoint: dict[str, Any],
    *,
    partial: bool = False,
) -> None:
    job = owned_job(connection, job_id, owner, now)
    if stage != job["stage"]:
        raise ProviderError("stage_conflict")
    checkpoints = dict(job["checkpoints"]) | {stage: checkpoint}
    final = stage == CHANNEL_ANALYSIS_STAGES[-1]
    connection.execute(
        update(s.jobs)
        .where(s.jobs.c.id == job_id)
        .values(
            checkpoints=checkpoints,
            stage=(
                "done"
                if final
                else CHANNEL_ANALYSIS_STAGES[CHANNEL_ANALYSIS_STAGES.index(stage) + 1]
            ),
            status=("partial" if partial else "succeeded") if final else "running",
            lease_until=None if final else job["lease_until"],
        )
    )
    if final:
        connection.execute(
            update(s.analysis_runs)
            .where(s.analysis_runs.c.id == job["run_id"])
            .values(status="partial" if partial else "succeeded", finished_at=now)
        )
