import json
from datetime import datetime
from decimal import Decimal
from typing import Any

import pytest

from nicheradar.config import Settings
from nicheradar.integrations import youtube_cli
from nicheradar.integrations.contracts import Batch, Cost, Coverage, Operation, Provenance


class FixtureProvider:
    def __init__(self, *_: Any, **__: Any) -> None:
        pass

    async def fetch(self, operation: Operation, parameters: dict[str, Any], now: datetime) -> Batch:
        assert operation == Operation.VIDEOS
        assert parameters == {"id": "fixture_123"}
        return Batch(
            provenance=Provenance(
                provider="youtube",
                operation=operation,
                auth_scope="fixture",
                fetched_at=now,
            ),
            coverage=Coverage(returned=0, complete=True, selection_method="id_lookup"),
            costs=(
                Cost(
                    unit="youtube_quota",
                    maximum=Decimal(1),
                    actual=Decimal(1),
                    source="fixture",
                ),
            ),
        )


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Settings, "model_config", Settings.model_config | {"env_file": None})


def test_youtube_diagnostic_is_local_by_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["nicheradar-youtube"])
    monkeypatch.delenv("NR_YOUTUBE_API_KEY", raising=False)
    monkeypatch.delenv("NR_YOUTUBE_AUTH_SCOPE", raising=False)
    youtube_cli.main()
    report = json.loads(capsys.readouterr().out)
    assert report["network_requests"] == 0
    assert report["credential_material_present"] is False


def test_youtube_diagnostic_reports_one_unit_without_exposing_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    secret = "youtube-private-fixture-key"
    monkeypatch.setenv("NR_YOUTUBE_API_KEY", secret)
    monkeypatch.setenv("NR_YOUTUBE_AUTH_SCOPE", "fixture-project")
    monkeypatch.setattr(youtube_cli, "YouTubeProvider", FixtureProvider)
    monkeypatch.setattr("sys.argv", ["nicheradar-youtube", "--check-video", "fixture_123"])
    youtube_cli.main()
    output = capsys.readouterr().out
    assert secret not in output
    report = json.loads(output)
    assert report["status"] == "connection_checked"
    assert report["network_requests"] == 1
    assert report["quota_units"] == 1
