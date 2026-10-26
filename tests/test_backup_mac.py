import hashlib
import json
import os
import shutil
import stat
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, Engine, update

import scripts.backup_mac as backup_mac
from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.workers.queue import create_schedule
from scripts.backup_mac import (
    crypt,
    initialize,
    load_backup,
    plan_retention,
    prune_backups,
    restore_drill,
    save_backup,
)
from scripts.backup_snapshot import (
    BOOTSTRAP_TABLES,
    FLOW_TABLES,
    MARKET_TABLES,
    PILOT_TABLES,
    PROVIDER_EVIDENCE_TABLES,
    RESEARCH_TABLES,
    inspect_snapshot,
)
from tests.test_flow_research_schema import add_dossier, add_request
from tests.test_market_intel_schema import listing
from tests.test_persistence import NOW, seed_evidence


@pytest.mark.postgres
def test_bootstrap_snapshot_guard_and_active_schedule(db: Connection) -> None:
    profile = seed_profile(db, CreatorProfile(), initial_catalog())
    create_schedule(db, profile, NOW, {})
    report = inspect_snapshot(db)
    assert report["scope"] == "bootstrap-only"
    assert report["revision"] == "0017"
    db.execute(update(s.radar_schedules).values(paused=False))
    with pytest.raises(ValueError, match="radar_not_paused"):
        inspect_snapshot(db)


@pytest.mark.postgres
def test_snapshot_reports_provider_evidence_rows_as_excluded(db: Connection) -> None:
    seed_evidence(db)
    report = inspect_snapshot(db)
    excluded = cast(dict[str, int], report["excluded_rows"])
    assert excluded["raw_observations"] > 0 and excluded["provider_requests"] > 0
    counts = cast(dict[str, int], report["counts"])
    assert all(counts[name] == 0 for name in excluded)  # a restore sees them empty
    assert report["scope"] == "bootstrap-only"


@pytest.mark.postgres
def test_snapshot_accepts_pilot_data_and_reports_the_wider_scope(db: Connection) -> None:
    db.exec_driver_sql(
        "INSERT INTO channel_tokens (id, channel_id, token_hash, label, created_at) "
        "VALUES (gen_random_uuid(), 'canal-x', repeat('a', 64), 'mac', now())"
    )
    report = inspect_snapshot(db)
    assert report["scope"] == "bootstrap+pilots"


@pytest.mark.postgres
def test_snapshot_reports_an_enabled_real_provider_without_blocking(db: Connection) -> None:
    insert_record(
        db,
        "provider_policies",
        {
            "provider": "vidiq",
            "data_type": "video",
            "operation": "recent",
            "usage": "storage",
            "version": "fixture",
            "status": "enabled",
            "evidence_source": "not a real grant",
            "effective_at": NOW,
        },
    )
    assert inspect_snapshot(db)["enabled_real_providers"] == ["vidiq"]


@pytest.mark.postgres
def test_snapshot_rejects_unknown_tables(db: Connection) -> None:
    db.exec_driver_sql("CREATE TABLE unknown_backup_scope (id integer)")
    with pytest.raises(ValueError, match="unexpected_schema"):
        inspect_snapshot(db)


def test_private_key_is_preserved_and_symlinks_rejected(tmp_path: Path) -> None:
    root = tmp_path / "NicheRadar"
    initialize(root)
    key = root / "keys/backup.key"
    original = key.read_bytes()
    initialize(root)
    assert key.read_bytes() == original
    assert len(original) >= 64
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    linked = tmp_path / "linked"
    linked.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="private_owner_only_path_required"):
        initialize(linked)
    key.chmod(0o644)
    with pytest.raises(ValueError, match="private_owner_only_path_required"):
        initialize(root)


def test_encrypted_archive_roundtrip_tamper_and_wrong_key(tmp_path: Path) -> None:
    if not shutil.which("gpg"):
        pytest.skip("GnuPG required for encrypted backup test")
    root = tmp_path / "NicheRadar"
    initialize(root)
    payload = b"PGDMP synthetic private fixture; not a database"
    report: dict[str, object] = {
        "scope": "bootstrap-only",
        "revision": "0017",
        "created_at": NOW.isoformat(),
        "dump_sha256": hashlib.sha256(payload).hexdigest(),
    }
    archive = save_backup(root, report, payload)
    assert payload not in archive.read_bytes()
    assert stat.S_IMODE(archive.stat().st_mode) == 0o600
    assert load_backup(root, archive) == (report, payload)
    other = tmp_path / "other"
    initialize(other)
    with pytest.raises(ValueError, match="backup_decryption_failed"):
        load_backup(other, archive)
    corrupted = bytearray(archive.read_bytes())
    corrupted[-5] ^= 0x01
    with pytest.raises(ValueError, match="backup_decryption_failed"):
        crypt(bytes(corrupted), root / "keys/backup.key", decrypt=True)


def dump_and_restore(postgres_engine: Engine, tmp_path: Path) -> dict[str, object]:
    binary_dir = os.environ.get("NR_TEST_POSTGRES_BIN")
    if not binary_dir or not shutil.which("gpg"):
        pytest.skip("Local PostgreSQL binaries and GnuPG required for isolated restore drill")
    with postgres_engine.connect() as connection:
        report = inspect_snapshot(connection)
    url = postgres_engine.url
    environment = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    environment.update(
        PGHOST=str(url.query.get("host", url.host or "localhost")),
        PGPORT=str(url.query.get("port", url.port or 5432)),
        PGUSER=url.username or "",
        PGPASSWORD=url.password or "",
    )
    dump = subprocess.run(
        [
            str(Path(binary_dir) / "pg_dump"),
            "--dbname",
            url.database or "",
            "--schema=public",
            "--format=custom",
            "--no-owner",
            "--no-acl",
            *(f"--exclude-table-data=public.{n}" for n in sorted(PROVIDER_EVIDENCE_TABLES)),
        ],
        env=environment,
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout
    report.update(dump_sha256=hashlib.sha256(dump).hexdigest(), created_at=NOW.isoformat())
    root = tmp_path / "NicheRadar"
    initialize(root)
    archive = save_backup(root, report, dump)
    restored_report, restored_dump = load_backup(root, archive)
    result = restore_drill(restored_report, restored_dump, Path(binary_dir))
    assert result["restore_verified"] is True
    assert result["source_untouched"] is True
    with postgres_engine.connect() as connection:
        assert inspect_snapshot(connection)["counts"] == report["counts"]
    return report


@pytest.mark.postgres
def test_encrypted_public_schema_restores_in_fresh_cluster(
    postgres_engine: Engine, tmp_path: Path
) -> None:
    assert dump_and_restore(postgres_engine, tmp_path)["scope"] == "bootstrap-only"


@pytest.mark.postgres
def test_encrypted_research_data_restores_in_fresh_cluster(
    postgres_engine: Engine, tmp_path: Path
) -> None:
    """Committed market and flow rows survive dump, encryption and isolated restore."""
    from nicheradar.repositories import schema

    with postgres_engine.begin() as connection:
        listing_id = listing(connection)
        request = add_request(connection)
        add_dossier(connection, request)
    try:
        report = dump_and_restore(postgres_engine, tmp_path)
        counts: dict[str, int] = report["counts"]  # type: ignore[assignment]
        assert report["scope"] == "bootstrap+research"
        assert counts["marketplace_listings"] == 1
        assert counts["flow_research_requests"] == counts["flow_research_dossiers"] == 1
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(sa.delete(schema.flow_research_dossiers))
            connection.execute(
                sa.delete(schema.flow_research_requests).where(
                    schema.flow_research_requests.c.id == request
                )
            )
            connection.execute(
                sa.delete(schema.marketplace_listings).where(
                    schema.marketplace_listings.c.id == listing_id
                )
            )


def test_reviewed_table_groups_are_exact_and_disjoint() -> None:
    from nicheradar.repositories import schema

    assert MARKET_TABLES == {
        "market_scrape_runs",
        "marketplace_listings",
        "listing_observations",
        "listing_classifications",
        "listing_verifications",
        "niche_automation_priors",
        "market_niche_snapshots",
        "market_niche_decisions",
    }
    assert FLOW_TABLES == {"flow_research_requests", "flow_research_dossiers"}
    assert RESEARCH_TABLES == MARKET_TABLES | FLOW_TABLES
    groups = [BOOTSTRAP_TABLES, PILOT_TABLES, MARKET_TABLES, FLOW_TABLES]
    assert sum(len(group) for group in groups) == len(set().union(*groups))
    reviewed = set().union(*groups)
    assert reviewed <= set(schema.metadata.tables) | {"alembic_version"}
    # Provider evidence is classified apart: its schema is dumped, its rows are not.
    unreviewed = (set(schema.metadata.tables) | {"alembic_version"}) - reviewed
    assert unreviewed == set(PROVIDER_EVIDENCE_TABLES)
    assert {"raw_observations", "provider_requests", "topics", "ranking_snapshots"} <= unreviewed


@pytest.mark.postgres
def test_snapshot_scope_combines_pilots_and_research(db: Connection) -> None:
    add_request(db)
    report = inspect_snapshot(db)
    assert report["scope"] == "bootstrap+research"
    db.exec_driver_sql(
        "INSERT INTO channel_tokens (id, channel_id, token_hash, label, created_at) "
        "VALUES (gen_random_uuid(), 'canal-x', repeat('a', 64), 'mac', now())"
    )
    assert inspect_snapshot(db)["scope"] == "bootstrap+pilots+research"


@pytest.mark.postgres
def test_snapshot_reports_the_earliest_deletion_deadline_of_research(db: Connection) -> None:
    assert inspect_snapshot(db)["delete_after"] is None
    listing(db)  # retained for 183 days
    soon = NOW + timedelta(days=3)
    request = add_request(db, retain_until=soon)
    add_dossier(db, request, retain_until=NOW + timedelta(days=50))
    assert inspect_snapshot(db)["delete_after"] == soon.isoformat()


@pytest.mark.postgres
def test_snapshot_keeps_research_and_excludes_provider_evidence_together(db: Connection) -> None:
    add_request(db)
    seed_evidence(db)
    report = inspect_snapshot(db)
    assert report["scope"] == "bootstrap+research"
    assert cast(dict[str, int], report["excluded_rows"])["raw_observations"] > 0


@pytest.mark.postgres
def test_snapshot_still_pins_the_reviewed_schema_revision(db: Connection) -> None:
    add_request(db)
    db.exec_driver_sql("UPDATE alembic_version SET version_num = '0018'")
    with pytest.raises(ValueError, match="unreviewed_schema_revision"):
        inspect_snapshot(db)


def test_load_backup_accepts_every_reviewed_scope(tmp_path: Path) -> None:
    if not shutil.which("gpg"):
        pytest.skip("GnuPG required for encrypted backup test")
    root = tmp_path / "NicheRadar"
    initialize(root)
    payload = b"PGDMP synthetic private fixture; not a database"
    for scope in (
        "bootstrap-only",
        "bootstrap+pilots",
        "bootstrap+research",
        "bootstrap+pilots+research",
    ):
        report: dict[str, object] = {
            "scope": scope,
            "revision": "0017",
            "created_at": NOW.isoformat(),
            "dump_sha256": hashlib.sha256(payload).hexdigest(),
        }
        assert load_backup(root, save_backup(root, report, payload))[0]["scope"] == scope
    report["scope"] = "bootstrap+everything"
    with pytest.raises(ValueError, match="invalid_archive"):
        load_backup(root, save_backup(root, report, payload))


def archive_name(moment: datetime) -> str:
    return f"bootstrap-{moment:%Y%m%dT%H%M%SZ}-abcdef01.gpg"


def test_retention_keeps_seven_daily_and_four_weekly_and_deletes_the_rest() -> None:
    now = datetime(2026, 11, 30, 12, tzinfo=UTC)
    # One copy per day for 60 days, plus an extra, older copy on the newest day.
    entries: list[tuple[str, datetime, datetime | None]] = [
        (archive_name(now - timedelta(days=d)), now - timedelta(days=d), None) for d in range(60)
    ]
    entries.append((archive_name(now - timedelta(hours=5)), now - timedelta(hours=5), None))
    plan = plan_retention(entries, now)
    daily = {name for name, verdict in plan.items() if verdict == "keep:daily"}
    weekly = {name for name, verdict in plan.items() if verdict == "keep:weekly"}
    assert len(daily) == 7
    assert archive_name(now) in daily
    assert archive_name(now - timedelta(hours=5)) not in daily  # superseded the same day
    assert plan[archive_name(now - timedelta(hours=5))] == "delete:superseded"
    assert len(weekly) == 4
    assert len([v for v in plan.values() if v.startswith("keep")]) == 11
    assert all(
        verdict.startswith("delete") for name, verdict in plan.items() if name not in daily | weekly
    )


def test_retention_deletes_copies_past_their_data_deadline_even_if_recent() -> None:
    now = datetime(2026, 11, 30, 12, tzinfo=UTC)
    newest = (archive_name(now), now, now - timedelta(seconds=1))
    previous = (archive_name(now - timedelta(days=1)), now - timedelta(days=1), None)
    plan = plan_retention([newest, previous], now)
    assert plan[newest[0]] == "delete:expired"
    assert plan[previous[0]] == "keep:daily"


def test_retention_never_deletes_the_only_current_copy_by_count() -> None:
    now = datetime(2026, 11, 30, 12, tzinfo=UTC)
    only = (archive_name(now), now, now + timedelta(days=1))
    assert plan_retention([only], now) == {only[0]: "keep:daily"}


def test_prune_deletes_only_matching_local_archives_and_dry_run_deletes_nothing(
    tmp_path: Path,
) -> None:
    if not shutil.which("gpg"):
        pytest.skip("GnuPG required for encrypted backup test")
    root = tmp_path / "NicheRadar"
    initialize(root)
    payload = b"PGDMP synthetic private fixture; not a database"
    now = datetime(2026, 11, 30, 12, tzinfo=UTC)

    def make(moment: datetime, delete_after: datetime | None = None) -> Path:
        report: dict[str, object] = {
            "scope": "bootstrap+research",
            "revision": "0017",
            "created_at": moment.isoformat(),
            "dump_sha256": hashlib.sha256(payload).hexdigest(),
            "delete_after": delete_after.isoformat() if delete_after else None,
        }
        return save_backup(root, report, payload, now=moment)

    fresh = make(now)
    expired = make(now - timedelta(days=1), now - timedelta(hours=1))
    stale = [make(now - timedelta(days=d)) for d in range(40, 80)]
    stranger = root / "backups" / "notes.txt"
    stranger.write_text("not a backup")
    outside = root / "keys" / "backup.key"
    dry = prune_backups(root, now, apply=False)
    assert all(path.exists() for path in [fresh, expired, *stale, stranger, outside])
    assert expired.name in cast(list[str], dry["would_delete"])
    applied = prune_backups(root, now, apply=True)
    assert applied["deleted"] == dry["would_delete"]
    assert fresh.exists() and not expired.exists()
    assert stranger.exists() and outside.exists()
    # fresh + 6 stale fill the 7 daily slots; 4 older weekly copies survive; the rest is gone
    assert sum(path.exists() for path in stale) == 6 + 4


def test_prune_refuses_symlinked_archives(tmp_path: Path) -> None:
    if not shutil.which("gpg"):
        pytest.skip("GnuPG required for encrypted backup test")
    root = tmp_path / "NicheRadar"
    initialize(root)
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me")
    now = datetime(2026, 11, 30, 12, tzinfo=UTC)
    (root / "backups" / archive_name(now - timedelta(days=90))).symlink_to(victim)
    result = prune_backups(root, now, apply=True)
    assert victim.exists()
    assert result["deleted"] == []
    assert result["skipped_unsafe"] == [archive_name(now - timedelta(days=90))]


def _fake_ssh(env: list[str], ports: dict[str, object] | None = None):  # type: ignore[no-untyped-def]
    inspected = [
        {
            "Config": {"Env": env, "Image": "img:tag"},
            "Image": "sha256:abc",
            "HostConfig": {"PortBindings": ports or {}},
        }
    ]

    def fake(command: list[str], timeout: int = 60) -> bytes:
        return b"abcdef123456\n" if command[1] == "ps" else json.dumps(inspected).encode()

    return fake


@pytest.mark.parametrize("mode", ["synthetic", "live"])
def test_the_runtime_guard_accepts_a_paused_live_or_synthetic_service(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    env = [f"NR_MODE={mode}", "NR_RADAR_PAUSED=true", "NR_VIDIQ_TOKEN=x", "NR_LLM_API_KEY=y"]
    monkeypatch.setattr(backup_mac, "ssh", _fake_ssh(env))
    assert backup_mac.container("api")[0] == "abcdef123456"


@pytest.mark.parametrize(
    "env",
    [
        ["NR_MODE=live", "NR_RADAR_PAUSED=false"],
        ["NR_MODE=live"],
        ["NR_MODE=other", "NR_RADAR_PAUSED=true"],
    ],
)
def test_the_runtime_guard_still_requires_a_paused_radar_and_a_known_mode(
    monkeypatch: pytest.MonkeyPatch, env: list[str]
) -> None:
    monkeypatch.setattr(backup_mac, "ssh", _fake_ssh(env))
    with pytest.raises(ValueError, match="unsafe_runtime"):
        backup_mac.container("api")


def test_the_runtime_guard_still_rejects_published_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ["NR_MODE=live", "NR_RADAR_PAUSED=true"]
    monkeypatch.setattr(backup_mac, "ssh", _fake_ssh(env, {"8000/tcp": [{}]}))
    with pytest.raises(ValueError, match="unexpected_published_ports"):
        backup_mac.container("api")


def test_the_dump_leaves_out_the_rows_of_every_provider_evidence_table() -> None:
    command = backup_mac.dump_command("db1", "00000003-0000001B-1")
    excluded = {a.split("public.", 1)[1] for a in command if a.startswith("--exclude-table-data=")}
    assert excluded == set(PROVIDER_EVIDENCE_TABLES)
    assert "--schema=public" in command and command[-1] == "--snapshot=00000003-0000001B-1"
    assert not any(a.startswith("--table") or a == "--data-only" for a in command)


@pytest.mark.postgres
def test_the_deadline_comes_only_from_tables_the_dump_keeps(db: Connection) -> None:
    from scripts.backup_snapshot import copied_data_deadline

    add_request(db)
    kept = db.execute(sa.text("SELECT min(retain_until) FROM flow_research_requests")).scalar_one()
    seed_evidence(db)  # provider evidence has its own, earlier deadlines
    assert copied_data_deadline(db) == kept
