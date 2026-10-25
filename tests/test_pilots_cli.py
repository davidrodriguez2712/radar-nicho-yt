# tests/test_pilots_cli.py
import json
from pathlib import Path
from typing import Any

import pytest

from nicheradar.pilots.cli import ApiError, PilotsClient, main


class FakeClient(PilotsClient):
    def __init__(self, reply: Any = None, fail: ApiError | None = None) -> None:
        self.calls: list[tuple[str, str, Any]] = []
        self.reply, self.fail = reply, fail

    def call(self, method: str, path: str, body: Any = None) -> Any:
        self.calls.append((method, path, body))
        if self.fail:
            raise self.fail
        return self.reply


def run(argv: list[str], client: FakeClient) -> int:
    return main(argv, client=client)


def test_authorize_maps_every_argument_and_never_defaults_the_language(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    client = FakeClient({"pilot_id": "pil_x"})
    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps([{"id": "r"}]))
    argv = [
        "authorize",
        "--niche-label",
        "n",
        "--format",
        "long",
        "--language",
        "en",
        "--dossier-id",
        "d",
        "--low",
        "3",
        "--likely",
        "19.5",
        "--high",
        "41",
        "--max-videos",
        "10",
        "--basis",
        "b",
        "--authorized-by",
        "david",
        "--target-channel",
        "canal-historias",
        "--recipe",
        "faceless-storytelling@0.1.0",
        "--stop-rules",
        str(rules),
    ]
    assert run(argv, client) == 0
    method, path, body = client.calls[0]
    assert (method, path) == ("POST", "/pilots")
    assert body["language"] == "en" and body["budget"]["likely"] == 19.5
    assert body["recipe"] == {"name": "faceless-storytelling", "version": "0.1.0"}
    assert body["stop_rules"] == [{"id": "r"}] and body["accept_no_go"] is False
    assert json.loads(capsys.readouterr().out) == {"pilot_id": "pil_x"}
    with pytest.raises(SystemExit):  # sin --language el comando no existe
        run([a for a in argv if a not in ("--language", "en")], client)


def test_decide_cancel_list_show_and_summary(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    client = FakeClient({"ok": True})
    assert run(["decide", "pil_x", "cerrar", "--note", "no rinde"], client) == 0
    assert client.calls[-1] == (
        "POST",
        "/pilots/pil_x/decision",
        {"decision": "cerrar", "note": "no rinde", "actor": "humano"},
    )
    assert run(["cancel", "pil_x", "--reason", "x"], client) == 0
    assert run(["list", "--status", "cerrado"], client) == 0
    last = client.calls[-1]
    assert last[1] == "/pilots?status=cerrado"
    assert run(["show", "pil_x"], client) == 0
    out = tmp_path / "evd.md"
    text = FakeClient("# EVD-x\n")
    assert run(["summary", "pil_x", "--out", str(out)], text) == 0
    assert out.read_text() == "# EVD-x\n"
    capsys.readouterr()


def test_a_new_channel_token_is_shown_once_with_a_warning(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = FakeClient({"token": "nrc_abc", "id": "1"})
    assert run(["token-issue", "--channel", "canal-historias", "--label", "mac"], client) == 0
    captured = capsys.readouterr()
    assert "nrc_abc" in captured.out and "no se puede volver a mostrar" in captured.err
    assert run(["token-list"], FakeClient({"items": []})) == 0
    assert run(["token-revoke", "abc"], FakeClient()) == 0


def test_api_errors_return_a_nonzero_code_without_a_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = FakeClient(fail=ApiError(409, {"code": "channel_busy"}))
    assert run(["cancel", "pil_x", "--reason", "x"], client) == 1
    assert "channel_busy" in capsys.readouterr().err
