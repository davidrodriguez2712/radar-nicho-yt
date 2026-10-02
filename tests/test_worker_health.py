import json
from pathlib import Path

from nicheradar.workers.health import healthy, record


def test_health_requires_recent_successful_database_tick(tmp_path: Path) -> None:
    path = tmp_path / "heartbeat.json"
    assert not healthy(path)
    record({"database": "ready", "status": "paused"}, 30, path)
    assert healthy(path)
    payload = json.loads(path.read_text())
    payload["at"] -= 301
    path.write_text(json.dumps(payload))
    assert not healthy(path)
    record({"status": "error", "error_code": "database_unavailable"}, 30, path)
    assert not healthy(path)
    path.write_text("broken")
    assert not healthy(path)
