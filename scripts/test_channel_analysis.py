"""Unpause, queue one real channel analysis, observe it to completion, and always pause again.

PUT /radar toggles a single global pause flag shared with the scheduled catalog-
discovery radar (workers/main.py's tick() claims from the SAME job queue for both,
with external_concurrency=1 serializing them) -- unpausing here can accidentally wake
a real, overdue scheduled discovery run that then starves this test's own job of the
worker's single concurrency slot (observed directly: a due "radar" schedule woke up the
moment this unpaused, and every channel-analysis attempt failed with attempts_exhausted
while that real job monopolized the worker). Deferring the schedule's own next_due_at
past "now" before unpausing -- only when it is currently due -- avoids this without
touching any real scheduling semantics: the scheduled run still fires at its next
regular interval, just not inside this test's brief window.
"""

import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
from sqlalchemy import select, update

from nicheradar.config import Settings
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.database import database_engine

channel_input = sys.argv[1]
# This runs inside the API container (needed for defer_due_radar_schedule()'s direct
# NR_DATABASE_URL access, which the dashboard container's environment does not have).
# NR_API_URL is unset there; config.py's own api_url default (the API reaching itself
# on its own loopback bind) is the correct fallback.
base = os.environ.get("NR_API_URL", "http://127.0.0.1:8000").rstrip("/") + "/api/v1"
headers = {"Authorization": f"Bearer {os.environ['NR_SERVICE_TOKEN']}"}


def request(method: str, path: str, **kwargs: object) -> dict[str, object]:
    merged_headers = {**headers, **kwargs.pop("headers", {})}
    response = httpx.request(method, base + path, headers=merged_headers, timeout=15, **kwargs)
    if response.status_code >= 400:
        raise SystemExit(f"{method} {path} -> {response.status_code}: {response.text}")
    return response.json()


def defer_due_radar_schedule() -> None:
    engine = database_engine(Settings())
    now = datetime.now(UTC)
    with engine.begin() as connection:
        schedule = (
            connection.execute(
                select(s.radar_schedules.c.next_due_at, s.radar_schedules.c.interval_seconds).where(
                    s.radar_schedules.c.schedule_key == "radar"
                )
            )
            .mappings()
            .one()
        )
        if schedule["next_due_at"] <= now:
            connection.execute(
                update(s.radar_schedules)
                .where(s.radar_schedules.c.schedule_key == "radar")
                .values(next_due_at=now + timedelta(seconds=schedule["interval_seconds"]))
            )
    engine.dispose()


result: dict[str, object] | None = None
job_id: str | None = None
try:
    defer_due_radar_schedule()
    request("PUT", "/radar", json={"paused": False})
    queued = request(
        "POST",
        "/channel-analyses",
        json={"channel_input": channel_input},
        headers={"Idempotency-Key": str(uuid4())},
    )
    job_id = str(queued["job_id"])
    deadline = time.monotonic() + 420
    while time.monotonic() < deadline:
        job = request("GET", f"/jobs/{job_id}")
        if job["status"] in {"succeeded", "partial", "deferred", "failed"}:
            result = job
            break
        time.sleep(5)
finally:
    request("PUT", "/radar", json={"paused": True})

if result is None:
    raise SystemExit(f"channel analysis did not finish before timeout (job {job_id})")

analyses = request("GET", "/channel-analyses?limit=5")["items"]
saved = next((item for item in analyses if item.get("run_id") == result.get("run_id")), None)
detail = request("GET", f"/channel-analyses/{saved['id']}") if saved else None
snapshot = (detail or {}).get("snapshot") or {}
metrics = snapshot.get("metrics", {})
status = request("GET", "/status")

print(
    json.dumps(
        {
            "job_id": result["id"],
            "status": result["status"],
            "error_code": result["error_code"],
            "coverage": result.get("coverage"),
            "consumption": result.get("consumption"),
            "source_mode": result.get("source_mode"),
            "radar_paused_after": status["radar_paused"],
            "live_pipeline": status["live_pipeline"],
            "analysis_id": (saved or {}).get("id"),
            "analysis_status": (saved or {}).get("status"),
            "channel_external_id": (saved or {}).get("channel_external_id"),
            "target_position": metrics.get("target_position"),
            "panorama_status": metrics.get("panorama", {}).get("status"),
            "panorama_metrics": metrics.get("panorama", {}).get("metrics"),
            "profit_status": metrics.get("profit", {}).get("status")
            if isinstance(metrics.get("profit"), dict)
            else None,
            "profit": metrics.get("profit"),
        }
    )
)
if result["status"] not in {"succeeded", "partial"} or not status["radar_paused"]:
    raise SystemExit(1)
