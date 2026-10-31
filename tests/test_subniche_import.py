# tests/test_subniche_import.py
import base64
import json
from pathlib import Path
from typing import Any

import pytest
from pytest import CaptureFixture
from sqlalchemy import Connection, Engine

from nicheradar.config import Settings
from nicheradar.market_intel.classify import niche_labels
from nicheradar.subniche_discovery.cli import main
from nicheradar.subniche_discovery.importer import (
    ImportFormatError,
    import_hypotheses,
    parse_export,
)
from nicheradar.subniche_discovery.store import (
    create_proposed,
    export_yaml,
    get_hypothesis,
    list_hypotheses,
)
from tests.subniche_samples import NOW, draft

REAL_FILE = Path(__file__).resolve().parent.parent / "config" / "subniche_hypotheses.yaml"
SEED = "UC" + "s" * 22
PARENT = "historical_stories"

BLOCK = """- slug: "history_revenge"
  label: "History Revenge Stories"
  family: "history"
  parent_niche: "historical_stories"
  queries: ["history revenge", "revenge that changed history"]
  origin: "manual"
  status: "proposed"
  finalist: false
  seed_channels: []
"""


def block(
    slug: str = "history_revenge",
    queries: str = '["history revenge", "revenge that changed history"]',
    parent: str = '"historical_stories"',
    status: str = '"proposed"',
    finalist: str = "false",
    seeds: str = "[]",
) -> str:
    return (
        f'- slug: "{slug}"\n  label: "Label {slug}"\n  family: "history"\n'
        f'  parent_niche: {parent}\n  queries: {queries}\n  origin: "manual"\n'
        f"  status: {status}\n  finalist: {finalist}\n  seed_channels: {seeds}\n"
    )


def two(extra: str = "") -> str:
    return (
        block("first_one", '["first query", "first other"]')
        + block("second_one", '["second query", "second other"]')
        + extra
    )


def test_parser_reads_a_real_block() -> None:
    items = parse_export(BLOCK)
    assert items == [
        {
            "slug": "history_revenge",
            "label": "History Revenge Stories",
            "family": "history",
            "parent_niche": "historical_stories",
            "queries": ["history revenge", "revenge that changed history"],
            "origin": "manual",
            "status": "proposed",
            "finalist": False,
            "seed_channels": [],
        }
    ]


def test_parser_ignores_blank_lines_and_empty_text() -> None:
    assert parse_export("") == []
    assert len(parse_export("\n" + BLOCK + "\n\n" + BLOCK.replace("revenge", "other"))) == 2


def test_parser_errors_carry_the_line_number() -> None:
    with pytest.raises(ImportFormatError, match="line 4"):
        parse_export(
            BLOCK.replace('  family: "history"\n', '  family: "history"\n  color: "x"\n', 1)
        )
    with pytest.raises(ImportFormatError, match="line 2"):
        parse_export('- slug: "abc"\n  label: not json\n')
    with pytest.raises(ImportFormatError, match="line 1"):
        parse_export('  label: "x"\n' + BLOCK)


def test_parser_garbage_line_number_is_exact() -> None:
    text = "\n" + BLOCK + "garbage line\n"
    with pytest.raises(ImportFormatError, match=f"line {len(text.splitlines())}:"):
        parse_export(text)


def test_parser_requires_the_mandatory_keys() -> None:
    incomplete = '- slug: "abc"\n  label: "Label"\n  family: "history"\n  origin: "manual"\n'
    with pytest.raises(ImportFormatError, match="line 1.*queries"):
        parse_export(incomplete)


def test_parser_rejects_duplicate_keys_in_a_block() -> None:
    with pytest.raises(ImportFormatError, match="line 3"):
        parse_export('- slug: "abc"\n  label: "Label"\n  label: "Other"\n')


def test_parser_limits_blocks_and_size() -> None:
    many = "".join(block(f"slug_{n:03d}") for n in range(501))
    with pytest.raises(ImportFormatError, match="500"):
        parse_export(many)
    with pytest.raises(ImportFormatError, match="200000"):
        parse_export("#" * 200_001)


@pytest.mark.postgres
def test_the_shipped_file_is_loadable(db: Connection) -> None:
    items = parse_export(REAL_FILE.read_text(encoding="utf-8"))
    assert len(items) == 60
    result = import_hypotheses(db, items, niche_labels(db), NOW, dry_run=True)
    assert result["ok"] is True and "invalid" not in result
    assert len(result["imported"]) == 60 and result["skipped"] == []
    assert list_hypotheses(db) == []


@pytest.mark.postgres
def test_import_creates_proposed_rows_and_ignores_status_and_finalist(db: Connection) -> None:
    seeds = f'["{SEED}"]'
    items = parse_export(
        block(status='"active"', finalist="true", seeds=seeds)
        + block("second_one", '["second query"]', parent="null")
    )
    result = import_hypotheses(db, items, niche_labels(db), NOW)
    assert result == {
        "ok": True,
        "dry_run": False,
        "imported": ["history_revenge", "second_one"],
        "skipped": [],
        "total": 2,
    }
    first = get_hypothesis(db, "history_revenge")
    assert first["status"] == "proposed" and first["finalist"] is False
    assert first["queries"] == ["history revenge", "revenge that changed history"]
    assert first["parent_niche_slug"] == PARENT and first["seed_channels"] == [SEED]
    assert first["approved_at"] is None
    assert get_hypothesis(db, "second_one")["parent_niche_slug"] is None


@pytest.mark.postgres
def test_reimport_is_idempotent(db: Connection) -> None:
    items = parse_export(two())
    import_hypotheses(db, items, niche_labels(db), NOW)
    again = import_hypotheses(db, items, niche_labels(db), NOW)
    assert again["ok"] is True and again["imported"] == [] and again["total"] == 2
    assert again["skipped"] == [
        {"slug": "first_one", "reason": "slug"},
        {"slug": "second_one", "reason": "slug"},
    ]
    assert len(list_hypotheses(db)) == 2


@pytest.mark.postgres
def test_one_invalid_item_writes_nothing_and_is_named(db: Connection) -> None:
    items = parse_export(two(block("third_one", '["third query"]', parent='"no_such_niche"')))
    result = import_hypotheses(db, items, niche_labels(db), NOW)
    assert result["ok"] is False
    assert [entry["slug"] for entry in result["invalid"]] == ["third_one"]
    assert list_hypotheses(db) == []


@pytest.mark.postgres
def test_all_invalid_items_are_collected(db: Connection) -> None:
    items = parse_export(
        block("bad slug!")
        + block("good_one", '["good query"]', parent='"nope"')
        + block("fine_one", '["fine query"]')
    )
    result = import_hypotheses(db, items, niche_labels(db), NOW)
    assert result["ok"] is False
    assert [entry["slug"] for entry in result["invalid"]] == ["bad slug!", "good_one"]
    assert all(entry["error"] for entry in result["invalid"])
    assert list_hypotheses(db) == []


@pytest.mark.postgres
def test_duplicates_inside_the_file_are_invalid(db: Connection) -> None:
    same_slug = parse_export(
        block("dup_slug", '["one query"]') + block("dup_slug", '["two query"]')
    )
    result = import_hypotheses(db, same_slug, niche_labels(db), NOW)
    assert result["ok"] is False and [e["slug"] for e in result["invalid"]] == ["dup_slug"]
    same_query = parse_export(
        block("slug_aaa", '["shared query"]') + block("slug_bbb", '["Shared Query!"]')
    )
    result = import_hypotheses(db, same_query, niche_labels(db), NOW)
    assert result["ok"] is False and [e["slug"] for e in result["invalid"]] == ["slug_bbb"]
    assert list_hypotheses(db) == []


@pytest.mark.postgres
def test_dry_run_writes_nothing_but_reports_the_same_numbers(db: Connection) -> None:
    create_proposed(db, draft("first_one", ("first query", "first other")), NOW)
    items = parse_export(two())
    before = len(list_hypotheses(db))
    dry = import_hypotheses(db, items, niche_labels(db), NOW, dry_run=True)
    assert len(list_hypotheses(db)) == before
    real = import_hypotheses(db, items, niche_labels(db), NOW)
    assert dry["dry_run"] is True and real["dry_run"] is False
    assert {k: v for k, v in dry.items() if k != "dry_run"} == {
        k: v for k, v in real.items() if k != "dry_run"
    }
    assert dry["imported"] == ["second_one"]
    assert dry["skipped"] == [{"slug": "first_one", "reason": "slug"}]


@pytest.mark.postgres
def test_round_trip_through_export_yaml(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        create_proposed(connection, draft("alpha_one", ("alpha query",), parent=PARENT), NOW)
        create_proposed(
            connection, draft("beta_two", ("beta query", "beta more"), seeds=(SEED,)), NOW
        )
        text = export_yaml(connection)
        connection.exec_driver_sql("DELETE FROM hypothesis_seed_channels")
        connection.exec_driver_sql("DELETE FROM niche_hypotheses")
        result = import_hypotheses(connection, parse_export(text), niche_labels(connection), NOW)
        assert result["imported"] == ["alpha_one", "beta_two"]
        rows = {
            row["slug"]: get_hypothesis(connection, row["slug"])
            for row in list_hypotheses(connection)
        }
    assert rows["alpha_one"]["queries"] == ["alpha query"]
    assert rows["alpha_one"]["parent_niche_slug"] == PARENT
    assert rows["beta_two"]["queries"] == ["beta query", "beta more"]
    assert rows["beta_two"]["seed_channels"] == [SEED]


# ---------------------------------------------------------------- CLI


def run(engine: Engine, capsys: CaptureFixture[str], *argv: str) -> tuple[int, dict[str, Any]]:
    code = main(list(argv), config=Settings(mode="live"), engine=engine, clock=lambda: NOW)
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    return code, json.loads(lines[-1]) if lines else {}


def b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def slugs(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        return [row["slug"] for row in list_hypotheses(connection)]


@pytest.mark.postgres
def test_cli_imports_from_a_path(
    isolated_engine: Engine, capsys: CaptureFixture[str], tmp_path: Path
) -> None:
    target = tmp_path / "in.yaml"
    target.write_text(two(), encoding="utf-8")
    code, out = run(isolated_engine, capsys, "import", str(target))
    assert code == 0 and out["imported"] == ["first_one", "second_one"] and out["total"] == 2
    assert slugs(isolated_engine) == ["first_one", "second_one"]
    code, out = run(isolated_engine, capsys, "import", str(target))
    assert code == 0 and out["imported"] == [] and len(out["skipped"]) == 2


@pytest.mark.postgres
def test_cli_b64_is_equivalent_to_a_path(
    isolated_engine: Engine, capsys: CaptureFixture[str]
) -> None:
    code, out = run(isolated_engine, capsys, "import", "--b64", b64(two()))
    assert code == 0 and out["ok"] is True and out["imported"] == ["first_one", "second_one"]
    assert slugs(isolated_engine) == ["first_one", "second_one"]


@pytest.mark.postgres
def test_cli_dry_run_writes_nothing(isolated_engine: Engine, capsys: CaptureFixture[str]) -> None:
    code, out = run(isolated_engine, capsys, "import", "--b64", b64(two()), "--dry-run")
    assert code == 0 and out["dry_run"] is True and len(out["imported"]) == 2
    assert slugs(isolated_engine) == []


@pytest.mark.postgres
def test_cli_invalid_items_exit_one_and_write_nothing(
    isolated_engine: Engine, capsys: CaptureFixture[str]
) -> None:
    text = two(block("third_one", '["third query"]', parent='"no_such_niche"'))
    code, out = run(isolated_engine, capsys, "import", "--b64", b64(text))
    assert code == 1 and out["error"] == "invalid_import"
    assert [entry["slug"] for entry in out["invalid"]] == ["third_one"]
    assert slugs(isolated_engine) == []


@pytest.mark.postgres
def test_cli_format_and_input_errors(
    isolated_engine: Engine, capsys: CaptureFixture[str], tmp_path: Path
) -> None:
    code, out = run(isolated_engine, capsys, "import", "--b64", "%%%not-base64%%%")
    assert code == 1 and out["error"] == "invalid_format"
    code, out = run(
        isolated_engine, capsys, "import", "--b64", base64.b64encode(b"\xff\xfe").decode()
    )
    assert code == 1 and out["error"] == "invalid_format"
    code, out = run(isolated_engine, capsys, "import", "--b64", b64("- slug: nope\n"))
    assert code == 1 and out["error"] == "invalid_format" and "line 1" in out["detail"]
    code, out = run(isolated_engine, capsys, "import", str(tmp_path / "missing.yaml"))
    assert code == 1 and out == {"error": "file_not_found"}
    assert slugs(isolated_engine) == []


@pytest.mark.postgres
def test_cli_requires_exactly_one_source(
    isolated_engine: Engine, capsys: CaptureFixture[str], tmp_path: Path
) -> None:
    with pytest.raises(SystemExit):
        main(["import"], config=Settings(mode="live"), engine=isolated_engine)
    with pytest.raises(SystemExit):
        main(
            ["import", str(tmp_path / "x"), "--b64", b64(two())],
            config=Settings(mode="live"),
            engine=isolated_engine,
        )
    capsys.readouterr()
