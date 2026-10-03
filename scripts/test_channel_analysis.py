"""Unpause, queue one real channel analysis, observe it to completion, and always pause again."""

import json
import os
import sys
import time
from uuid import uuid4

import httpx

channel_input = sys.argv[1]
base = os.environ["NR_API_URL"].rstrip("/") + "/api/v1"
headers = {"Authorization": f"Bearer {os.environ['NR_SERVICE_TOKEN']}"}


def request(method: str, path: str, **kwargs: object) -> dict[str, object]:
    merged_headers = {**headers, **kwargs.pop("headers", {})}
    response = httpx.request(method, base + path, headers=merged_headers, timeout=15, **kwargs)
    if response.status_code >= 400:
        raise SystemExit(f"{method} {path} -> {response.status_code}: {response.text}")
    return response.json()


result: dict[str, object] | None = None
job_id: str | None = None
try:
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
