# tests/test_subniche_cli.py
import json
from pathlib import Path
from typing import Any

import pytest
from pytest import CaptureFixture
from sqlalchemy import Engine

from nicheradar.config import Settings
from nicheradar.subniche_discovery.cli import main
from tests.subniche_samples import NOW


def run(engine: Engine, capsys: CaptureFixture[str], *argv: str) -> tuple[int, dict[str, Any]]:
    code = main(list(argv), config=Settings(mode="live"), engine=engine, clock=lambda: NOW)
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    return code, json.loads(lines[-1]) if lines else {}


ADD = ("add", "history revenge", "--manual", "--label", "History Revenge", "--family", "history")


@pytest.mark.postgres
def test_manual_add_approve_finalist_pause_and_list(
    isolated_engine: Engine, capsys: CaptureFixture[str]
) -> None:
    code, out = run(isolated_engine, capsys, *ADD)
    assert code == 0 and out["status"] == "proposed"
    assert run(isolated_engine, capsys, "approve", "history_revenge")[0] == 0
    assert run(isolated_engine, capsys, "finalist", "history_revenge")[0] == 0
    code, out = run(isolated_engine, capsys, "list", "--status", "active")
    assert code == 0 and [row["slug"] for row in out["hypotheses"]] == ["history_revenge"]
    assert run(isolated_engine, capsys, "pause", "history_revenge")[0] == 0
    assert run(isolated_engine, capsys, "resume", "history_revenge")[0] == 0
    assert run(isolated_engine, capsys, "measure", "history_revenge")[0] == 0
    assert run(isolated_engine, capsys, "archive", "history_revenge")[0] == 0


@pytest.mark.postgres
def test_errors_exit_nonzero_with_a_json_reason(
    isolated_engine: Engine, capsys: CaptureFixture[str]
) -> None:
    code, out = run(isolated_engine, capsys, "approve", "does_not_exist")
    assert code == 1 and out["error"] == "unknown_hypothesis"
    run(isolated_engine, capsys, *ADD)
    run(isolated_engine, capsys, "approve", "history_revenge")
    code, out = run(isolated_engine, capsys, "approve", "history_revenge")
    assert code == 1 and out["error"] == "invalid_transition"


@pytest.mark.postgres
def test_export_prints_yaml_and_can_write_a_file(
    isolated_engine: Engine, capsys: CaptureFixture[str], tmp_path: Path
) -> None:
    run(isolated_engine, capsys, *ADD)
    main(["export"], config=Settings(mode="live"), engine=isolated_engine, clock=lambda: NOW)
    assert '- slug: "history_revenge"' in capsys.readouterr().out
    target = tmp_path / "out.yaml"
    main(
        ["export", "--out", str(target)],
        config=Settings(mode="live"),
        engine=isolated_engine,
        clock=lambda: NOW,
    )
    assert '- slug: "history_revenge"' in target.read_text(encoding="utf-8")
