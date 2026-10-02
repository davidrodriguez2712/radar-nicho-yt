"""Local heartbeat probe: no HTTP endpoint, credentials or provider calls."""

import json
import time
from pathlib import Path

HEARTBEAT = Path("/tmp/nicheradar-worker-health.json")


def record(status: dict[str, object], poll_seconds: int, path: Path = HEARTBEAT) -> None:
    payload = {
        "at": time.time(),
        "max_age": max(300, poll_seconds * 3),
        "healthy": status.get("database") == "ready" and status.get("status") != "error",
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload))
    temporary.replace(path)


def healthy(path: Path = HEARTBEAT) -> bool:
    try:
        payload = json.loads(path.read_text())
        age = time.time() - payload["at"]
        return payload["healthy"] is True and 0 <= age <= payload["max_age"]
    except (OSError, ValueError, KeyError, TypeError):
        return False


if __name__ == "__main__":
    raise SystemExit(0 if healthy() else 1)
