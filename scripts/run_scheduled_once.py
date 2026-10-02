"""Unpause one deployed scheduled occurrence, observe it, and always pause again."""

import json
import os
import time

import httpx

base = os.environ["NR_API_URL"].rstrip("/") + "/api/v1"
headers = {"Authorization": f"Bearer {os.environ['NR_SERVICE_TOKEN']}"}


def request(method: str, path: str, **kwargs: object) -> dict[str, object]:
    response = httpx.request(method, base + path, headers=headers, timeout=15, **kwargs)
    response.raise_for_status()
    return response.json()


before = {item["id"] for item in request("GET", "/jobs?limit=100")["items"]}
result: dict[str, object] | None = None
try:
    request("PUT", "/radar", json={"paused": False})
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        jobs = request("GET", "/jobs?limit=20")["items"]
        fresh = [item for item in jobs if item["id"] not in before]
        if fresh and fresh[0]["status"] in {"succeeded", "partial", "deferred", "failed"}:
            result = fresh[0]
            break
        time.sleep(5)
finally:
    request("PUT", "/radar", json={"paused": True})

if result is None:
    raise SystemExit("scheduled occurrence did not finish before timeout")
status = request("GET", "/status")
print(
    json.dumps(
        {
            "job_id": result["id"],
            "status": result["status"],
            "error_code": result["error_code"],
            "coverage": result["coverage"],
            "consumption": result["consumption"],
            "source_mode": result["source_mode"],
            "radar_paused_after": status["radar_paused"],
            "live_pipeline": status["live_pipeline"],
        }
    )
)
if (
    result["status"] not in {"succeeded", "partial"}
    or result["source_mode"] != "live"
    or not status["radar_paused"]
):
    raise SystemExit(1)
