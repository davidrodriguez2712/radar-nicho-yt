# tests/test_channel_human_minutes.py
"""channel_human_minutes.py: lector de registros de sesión (solo marcas de tiempo, nunca texto)."""

import json
import re
from collections.abc import Mapping
from pathlib import Path

import pytest

from scripts import channel_human_minutes as hm


def jsonl(tmp_path: Path, name: str, records: list[object]) -> Path:
    path = tmp_path / name
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", "utf-8")
    return path


def event(kind: str, at: str, session: str = "s1", content: object = "hola") -> dict[str, object]:
    return {
        "type": kind,
        "timestamp": f"2026-11-03T{at}Z",
        "sessionId": session,
        "message": {"content": content},
    }


@pytest.mark.parametrize(
    "record",
    [
        {"type": "user", "message": {"content": "hola"}},
        {"type": "user", "message": {"content": [{"type": "text", "text": "hola"}]}},
    ],
)
def test_human_prompt_true(record: Mapping[str, object]) -> None:
    assert hm.is_human_prompt(record)


@pytest.mark.parametrize(
    "record",
    [
        {"type": "user", "isMeta": True, "message": {"content": "x"}},
        {"type": "user", "isSidechain": True, "message": {"content": "x"}},
        {"type": "user", "toolUseResult": {"a": 1}, "message": {"content": "x"}},
        {"type": "user", "message": {"content": [{"type": "tool_result"}]}},
        {
            "type": "user",
            "message": {"content": [{"type": "text"}, {"type": "tool_result"}]},
        },
        {"type": "assistant", "message": {"content": "x"}},
        {"type": "system", "message": {"content": "x"}},
        {"type": "user", "message": {"content": None}},
        {"type": "user", "message": {"content": []}},
        {"type": "user", "message": {"content": 5}},
        {"type": "user", "message": {"content": "   "}},
        {"type": "user"},
    ],
)
def test_human_prompt_false(record: Mapping[str, object]) -> None:
    assert not hm.is_human_prompt(record)


def test_gaps_are_capped(tmp_path: Path) -> None:
    f = jsonl(
        tmp_path,
        "a.jsonl",
        [
            event("assistant", "10:00:00"),
            event("user", "10:00:30"),
            event("assistant", "10:20:00"),
            event("user", "10:50:00"),
        ],
    )
    prompts = hm.read_human_prompts([f], 900)
    assert [p.gap_seconds for p in prompts] == [30, 900]
    assert all(p.at.tzinfo is not None for p in prompts)


def test_first_message_has_zero_gap(tmp_path: Path) -> None:
    f = jsonl(tmp_path, "a.jsonl", [event("user", "10:00:00")])
    assert [p.gap_seconds for p in hm.read_human_prompts([f], 900)] == [0]


def test_interleaved_sessions_do_not_mix(tmp_path: Path) -> None:
    f = jsonl(
        tmp_path,
        "a.jsonl",
        [
            event("assistant", "10:00:00", "A"),
            event("assistant", "10:00:50", "B"),
            event("user", "10:01:00", "A"),
            event("user", "10:01:10", "B"),
        ],
    )
    prompts = hm.read_human_prompts([f], 900)
    assert [p.gap_seconds for p in prompts] == [60, 20]


def test_corrupt_lines_are_skipped_and_result_sorted(tmp_path: Path) -> None:
    path = tmp_path / "a.jsonl"
    good_late = json.dumps(event("user", "11:00:00"))
    good_early = json.dumps(event("user", "10:00:00", "s2"))
    naive = json.dumps(
        {
            "type": "user",
            "timestamp": "2026-11-03T10:30:00",
            "sessionId": "s3",
            "message": {"content": "x"},
        }
    )
    bad = [
        '{"type": "user", "timestamp": "2026-11-03T1',
        json.dumps({"type": "user", "sessionId": "s1", "message": {"content": "x"}}),
        json.dumps(event("user", "10:00:00").copy() | {"timestamp": "basura"}),
        "[1, 2]",
        "",
    ]
    path.write_text("\n".join([good_late, *bad, naive, good_early]) + "\n", "utf-8")
    prompts = hm.read_human_prompts([path, tmp_path / "missing.jsonl"], 900)
    assert [p.at.isoformat() for p in prompts] == [
        "2026-11-03T10:00:00+00:00",
        "2026-11-03T10:30:00+00:00",
        "2026-11-03T11:00:00+00:00",
    ]


def test_huge_content_is_not_kept(tmp_path: Path) -> None:
    secret = "SECRETO" + "x" * (5 * 1024 * 1024)
    f = jsonl(tmp_path, "a.jsonl", [event("user", "10:00:00", content=secret)])
    prompts = hm.read_human_prompts([f], 900)
    assert len(prompts) == 1
    assert "SECRETO" not in repr(prompts)


def test_session_dirs_only_existing(tmp_path: Path) -> None:
    channel = tmp_path / "canal-ab.c"
    channel.mkdir()
    encoded = re.sub(r"[^A-Za-z0-9-]", "-", str(channel.resolve()))
    home_a, home_b = tmp_path / "a", tmp_path / "b"
    (home_b / "projects" / encoded).mkdir(parents=True)
    home_a.mkdir()
    assert hm.session_dirs(channel, [home_a, home_b]) == [home_b / "projects" / encoded]
    assert re.sub(r"[^A-Za-z0-9-]", "-", "/tmp/x/canal-ab.c") == "-tmp-x-canal-ab-c"


def test_deeply_nested_line_does_not_kill_the_read(tmp_path: Path) -> None:
    path = tmp_path / "a.jsonl"
    path.write_text("[" * 100_000 + "\n" + json.dumps(event("user", "10:00:00")) + "\n", "utf-8")
    assert len(hm.read_human_prompts([path], 900)) == 1


def test_extreme_timestamp_is_ignored(tmp_path: Path) -> None:
    extreme = event("user", "10:00:00") | {"timestamp": "0001-01-01T00:00:00+05:00"}
    f = jsonl(tmp_path, "a.jsonl", [extreme, event("user", "10:00:05")])
    assert len(hm.read_human_prompts([f], 900)) == 1


def test_unicode_line_separators_do_not_split_records(tmp_path: Path) -> None:
    path = tmp_path / "a.jsonl"
    record = event("user", "10:00:00", content="uno dos tres\x85\x0b\x0c")
    path.write_text(json.dumps(record, ensure_ascii=False) + "\n", "utf-8")
    assert len(hm.read_human_prompts([path], 900)) == 1


def test_invalid_utf8_does_not_raise(tmp_path: Path) -> None:
    path = tmp_path / "a.jsonl"
    good = json.dumps(event("user", "10:00:00")).encode()
    path.write_bytes(b'{"type": "user", "x": "\xff\xfe"}\n' + good + b"\n")
    assert len(hm.read_human_prompts([path], 900)) == 1


def test_output_stays_silent(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    secret = "SECRETO" + "x" * (5 * 1024 * 1024)
    f = jsonl(tmp_path, "a.jsonl", [event("user", "10:00:00", content=secret)])
    hm.read_human_prompts([f], 900)
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


def test_bad_session_id_and_unhashable_type_are_ignored(tmp_path: Path) -> None:
    f = jsonl(
        tmp_path,
        "a.jsonl",
        [
            event("user", "10:00:00") | {"sessionId": 7},
            {k: v for k, v in event("user", "10:00:01").items() if k != "sessionId"},
            event("user", "10:00:02") | {"type": ["user"]},
            event("user", "10:00:03") | {"type": {"a": 1}},
        ],
    )
    assert hm.read_human_prompts([f], 900) == []


def test_out_of_order_timestamps_give_zero_gap(tmp_path: Path) -> None:
    f = jsonl(tmp_path, "a.jsonl", [event("assistant", "10:10:00"), event("user", "10:00:00")])
    assert [p.gap_seconds for p in hm.read_human_prompts([f], 900)] == [0]
