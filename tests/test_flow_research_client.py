# tests/test_flow_research_client.py
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import Engine

from nicheradar.flow_research.cli import main
from nicheradar.flow_research.client import ApiError, FlowResearchClient
from tests.flow_research_samples import valid_dossier
from tests.test_flow_research_api import create, tentative_api
from tests.test_market_api import AUTH
from tests.test_persistence import NOW

SKILL = Path(".claude/skills/flow-research/SKILL.md")
FILE_NOW = datetime(2026, 10, 20, 15, tzinfo=UTC)


class Untouchable(FlowResearchClient):
    def __init__(self) -> None:
        pass

    def pending(self) -> list[dict[str, Any]]:
        raise AssertionError("the API must not be called")

    def claim(self, request_id: str, owner: str) -> dict[str, Any]:
        raise AssertionError("the API must not be called")

    def submit(self, request_id: str, owner: str, dossier: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("the API must not be called")


@pytest.mark.postgres
def test_the_client_round_trips_against_the_api(isolated_engine: Engine) -> None:
    api = tentative_api(isolated_engine)
    api.headers.update(AUTH)
    request_id = create(api)["id"]
    client = FlowResearchClient(api)
    assert [item["id"] for item in client.pending()] == [request_id]
    claimed = client.claim(request_id, "w1")
    assert claimed["status"] == "en_curso" and claimed["evidence"]["niche"]
    owner = claimed["lease_owner"]
    bad = client.submit(request_id, owner, {"x": 1})
    assert bad["accepted"] is False and bad["remaining_attempts"] == 1
    good = client.submit(request_id, owner, valid_dossier(UUID(request_id), NOW))
    assert good["accepted"] is True


@pytest.mark.postgres
def test_api_errors_never_leak_the_token(isolated_engine: Engine) -> None:
    api = tentative_api(isolated_engine)
    api.headers.update({"Authorization": "Bearer wrong-token-value"})
    with pytest.raises(ApiError) as error:
        FlowResearchClient(api).pending()
    assert error.value.status == 401 and "wrong-token-value" not in str(error.value)
    api.headers.update(AUTH)
    with pytest.raises(ApiError) as missing:
        FlowResearchClient(api).claim(str(uuid4()), "w1")
    assert missing.value.status == 404


def test_the_client_wraps_non_json_errors() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(502, text="bad gateway"))
    client = FlowResearchClient(httpx.Client(transport=transport, base_url="http://x"))
    with pytest.raises(ApiError) as error:
        client.pending()
    assert error.value.status == 502


def write(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "dossier.json"
    path.write_text(json.dumps(payload))
    return path


def test_validate_reports_every_problem(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good = write(tmp_path, valid_dossier(uuid4(), FILE_NOW))
    assert main(["validate", str(good)], now=lambda: FILE_NOW) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True
    broken = valid_dossier(uuid4(), FILE_NOW)
    broken["budget"]["lines"][0]["subtotal_usd"] = 41.0
    bad = write(tmp_path, broken)
    assert main(["validate", str(bad)], now=lambda: FILE_NOW) == 1
    printed = json.loads(capsys.readouterr().out)
    assert printed["valid"] is False
    assert "budget.lines.0.subtotal_usd" in {p["path"] for p in printed["problems"]}


def test_validate_survives_a_file_that_is_not_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json")
    assert main(["validate", str(path)], now=lambda: FILE_NOW) == 2


def test_submit_refuses_a_locally_invalid_dossier_without_calling_the_api(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = write(tmp_path, {"x": 1})
    code = main(
        ["submit", str(uuid4()), str(bad), "--owner", "w1"],
        client=Untouchable(),
        now=lambda: FILE_NOW,
    )
    assert code == 1 and json.loads(capsys.readouterr().out)["valid"] is False


def test_the_schema_command_prints_the_contract(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["schema"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert "verdict" in schema["properties"] and schema["title"] == "DossierV2"


def test_the_skill_names_every_command_and_forbids_leaking_the_token() -> None:
    text = SKILL.read_text()
    assert text.startswith("---\nname: flow-research\n")
    for command in ("pending", "claim", "schema", "validate", "submit"):
        assert f"scripts/flow_research.py {command}" in text
    assert "NR_SERVICE_TOKEN" in text and "nunca" in text.lower()
