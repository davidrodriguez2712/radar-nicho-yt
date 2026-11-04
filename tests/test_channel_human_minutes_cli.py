"""channel_human_minutes.py: conversión del outbox a channel-report-v3 y CLI."""

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from nicheradar.pilots.contracts import ReportV3, validate_report
from scripts import channel_human_minutes as hm
from scripts import channel_sync as sync
from tests.pilot_samples import NOW, report, video
from tests.shorts_report_samples import shorts_report, shorts_video

KNOWN = "v_20261103_a1b2"
SECRET = "SECRETO-DE-PRUEBA"


def message(minute: int, day: int = 3, year_month: str = "2026-11") -> dict[str, Any]:
    return {
        "type": "user",
        "timestamp": f"{year_month}-{day:02d}T10:{minute:02d}:00Z",
        "sessionId": "s1",
        "message": {"content": f"{SECRET} {minute}"},
    }


class Setup:
    def __init__(self, tmp_path: Path, video_ids: tuple[str, ...] = (KNOWN,)) -> None:
        self.channel = tmp_path / "canal"
        self.outbox = self.channel / ".nicheradar" / "outbox"
        self.outbox.mkdir(parents=True)
        self.sessions = tmp_path / "sesiones"
        self.sessions.mkdir()
        self.db = tmp_path / "pipeline.db"
        con = sqlite3.connect(self.db)
        con.execute(
            "CREATE TABLE eventos (id INTEGER PRIMARY KEY, video_id TEXT, de_estado TEXT, "
            "a_estado TEXT, rama TEXT, motivo TEXT, actor TEXT, creado_en TEXT)"
        )
        for video_id in video_ids:
            for state, at in (
                ("IDEA", "2026-11-03T10:00:00Z"),
                ("PUBLICADO", "2026-11-03T11:00:00Z"),
            ):
                con.execute(
                    "INSERT INTO eventos (video_id, a_estado, creado_en) VALUES (?,?,?)",
                    (video_id, state, at),
                )
        con.commit()
        con.close()
        self.write_session([message(0), message(10), message(20)])

    def write_session(self, records: list[dict[str, Any]]) -> None:
        text = "\n".join(json.dumps(r) for r in records) + "\n"
        (self.sessions / "s1.jsonl").write_text(text, "utf-8")

    def put(self, name: str, payload: object) -> Path:
        path = self.outbox / name
        path.write_text(json.dumps(payload), "utf-8")
        return path

    def run(self, *extra: str) -> int:
        return hm.main(
            [
                "--channel-dir", str(self.channel),
                "--db", str(self.db),
                "--sessions-dir", str(self.sessions),
                *extra,
            ],
            homes=[],
        )  # fmt: skip

    def snapshot(self) -> dict[str, bytes]:
        return {p.name: p.read_bytes() for p in sorted(self.outbox.iterdir()) if p.is_file()}


def load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text("utf-8"))
    assert isinstance(data, dict)
    return data


def test_long_report_is_converted_and_validates(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    original = report(
        video(KNOWN),
        video(
            "v_20261103_zzzz",
            published_at=None,
            source_state="GUION",
            visibility="private",
            measurement=None,
        ),
    )
    path = s.put("r.json", original)
    assert s.run() == 0
    converted = load(path)
    parsed, problems = validate_report(converted, NOW)
    assert problems == [] and isinstance(parsed, ReportV3)
    assert converted["format"] == "long"
    assert converted["human_minutes_method"] == "claude_sessions_plus_assumed"
    assert converted["videos"][0]["human_minutes"] == 20 + 10
    assert converted["videos"][1]["human_minutes"] is None
    stripped = {k: v for k, v in converted.items() if k not in ("format", "human_minutes_method")}
    stripped["contract"] = "channel-report-v1"
    stripped["videos"] = [
        {k: v for k, v in x.items() if k != "human_minutes"} for x in converted["videos"]
    ]
    assert stripped == original
    assert list(converted)[: len(original)] == list(original)  # orden de claves conservado


def test_shorts_report_is_converted(tmp_path: Path) -> None:
    s = Setup(tmp_path, ("s_01",))
    path = s.put("r.json", shorts_report([shorts_video(1)]))
    assert s.run() == 0
    converted = load(path)
    assert converted["format"] == "shorts"
    parsed, problems = validate_report(converted, NOW.replace(year=2027))
    assert problems == [] and isinstance(parsed, ReportV3)


def test_unknown_video_is_null_never_zero(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    path = s.put("r.json", report(video("v_20261103_desconocido")))
    assert s.run() == 0
    assert load(path)["videos"][0]["human_minutes"] is None


def test_unconvertible_files_stay_intact_and_fail(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    (s.outbox / "roto.json").write_text("{no es json", "utf-8")
    (s.outbox / "arreglo.json").write_text("[1, 2]", "utf-8")
    s.put("raro.json", {"contract": "otro-v9", "videos": []})
    before = s.snapshot()
    assert s.run() == 1
    assert s.snapshot() == before


def test_already_v3_is_skipped_without_failure(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    s.put("v3.json", {"contract": "channel-report-v3", "videos": []})
    before = s.snapshot()
    assert s.run() == 0
    assert s.snapshot() == before


def test_idempotent_and_orig_never_overwritten(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    original = report(video(KNOWN))
    s.put("r.json", original)
    assert s.run() == 0
    first = s.snapshot()
    assert json.loads(first["r.json.orig"]) == original
    assert s.run() == 0
    assert s.snapshot() == first
    (s.outbox / "r.json.orig").write_text("marca", "utf-8")
    s.put("r.json", report(video(KNOWN)))
    assert s.run() == 0
    assert (s.outbox / "r.json.orig").read_text("utf-8") == "marca"


def test_dry_run_changes_nothing(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    s.put("r.json", report(video(KNOWN)))
    before = s.snapshot()
    assert s.run("--dry-run") == 0
    assert s.snapshot() == before
    assert not list(s.outbox.glob("*.orig"))


def test_value_is_capped_at_100000(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    s.write_session(
        [message(0, 3), message(30, 3), {**message(40, 3), "timestamp": "2026-11-03T10:59:00Z"}]
    )
    con = sqlite3.connect(s.db)
    con.execute(
        "UPDATE eventos SET creado_en = '2028-01-01T00:00:00Z' WHERE a_estado = 'PUBLICADO'"
    )
    con.commit()
    con.close()
    s.write_session([message(0), {**message(0), "timestamp": "2027-06-01T10:00:00Z"}])
    path = s.put("r.json", report(video(KNOWN)))
    assert s.run("--cap-minutes", "999999999", "--assumed-minutes", "0") == 0
    assert load(path)["videos"][0]["human_minutes"] == 100_000


def test_output_never_contains_conversation_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    s = Setup(tmp_path)
    s.put("r.json", report(video(KNOWN)))
    s.run()
    captured = capsys.readouterr()
    assert SECRET not in captured.out + captured.err
    assert "minutos sin atribuir" in captured.out
    assert f"{KNOWN}: medido 20 · supuesto 10 = 30 min" in captured.out


def test_channel_sync_accepts_the_converted_file_unchanged(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    path = s.put("r.json", report(video(KNOWN)))
    assert s.run() == 0
    sent: list[tuple[str, str, Any]] = []

    def fake(method: str, url: str, body: Any = None) -> tuple[int, Any]:
        sent.append((method, url, body))
        return 200, {"pilot_status": "active", "warnings": []}

    errors: list[str] = []
    assert sync.report(fake, s.channel, "canal-historias", errors.append) == 0
    assert len(sent) == 1 and sent[0][2] == load(s.outbox / "sent" / path.name)
    assert sent[0][2]["contract"] == "channel-report-v3"
    assert not path.exists()


def test_warning_when_most_time_is_unattributed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    s = Setup(tmp_path)
    s.write_session([message(0), message(10), message(20, day=9), message(40, day=9)])
    s.run("--dry-run")
    out = capsys.readouterr().out
    assert "Aviso: más del 60 %" in out and "(" in out and " %)" in out


def test_no_warning_when_mostly_attributed_and_zero_total_is_safe(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    s = Setup(tmp_path)
    s.run("--dry-run")
    out = capsys.readouterr().out
    assert "Aviso" not in out and "(0 %)" in out
    s.write_session([])
    assert s.run("--dry-run") == 0
    assert "Aviso" not in capsys.readouterr().out


def test_backup_failure_leaves_no_orig_and_next_run_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = Setup(tmp_path)
    path = s.put("r.json", report(video(KNOWN)))
    before = path.read_bytes()
    real_replace = os.replace

    def boom(src: Any, dst: Any) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "replace", boom)
    assert s.run() == 1
    assert path.read_bytes() == before
    assert sorted(p.name for p in s.outbox.iterdir()) == ["r.json"]
    monkeypatch.setattr(os, "replace", real_replace)
    assert s.run() == 0
    assert (s.outbox / "r.json.orig").read_bytes() == before


def test_write_atomic_failure_removes_tmp_and_mode_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "x.json"
    target.write_text("{}", "utf-8")
    target.chmod(0o640)
    hm._write_atomic(target, {"a": 1})
    assert target.stat().st_mode & 0o777 == 0o640
    monkeypatch.setattr(os, "replace", lambda *_: (_ for _ in ()).throw(OSError(5, "x")))
    with pytest.raises(OSError):
        hm._write_atomic(target, {"a": 2})
    assert [p.name for p in tmp_path.iterdir()] == ["x.json"]


def test_symlinked_target_is_refused(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    real = tmp_path / "real.json"
    real.write_text(json.dumps(report(video(KNOWN))), "utf-8")
    (s.outbox / "link.json").symlink_to(real)
    before = real.read_bytes()
    assert s.run() == 1
    assert real.read_bytes() == before and not list(s.outbox.glob("*.orig"))


def test_format_is_set_from_the_contract(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    path = s.put("r.json", report(video(KNOWN), format="shorts"))
    assert s.run() == 0
    assert load(path)["format"] == "long"
