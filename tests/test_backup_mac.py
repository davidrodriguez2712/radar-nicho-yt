import hashlib
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, update

from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.workers.queue import create_schedule
from scripts.backup_mac import crypt, initialize, load_backup, restore_drill, save_backup
from scripts.backup_snapshot import inspect_snapshot
from tests.test_persistence import NOW, seed_evidence


@pytest.mark.postgres
def test_bootstrap_snapshot_guard_and_active_schedule(db: Connection) -> None:
    profile = seed_profile(db, CreatorProfile(), initial_catalog())
    create_schedule(db, profile, NOW, {})
    report = inspect_snapshot(db)
    assert report["scope"] == "bootstrap-only"
    assert report["revision"] == "0015"
    db.execute(update(s.radar_schedules).values(paused=False))
    with pytest.raises(ValueError, match="radar_not_paused"):
        inspect_snapshot(db)


@pytest.mark.postgres
def test_snapshot_rejects_research_even_in_synthetic_mode(db: Connection) -> None:
    seed_evidence(db)
    with pytest.raises(ValueError, match="research_data_backup_not_enabled"):
        inspect_snapshot(db)


@pytest.mark.postgres
def test_snapshot_accepts_pilot_data_and_reports_the_wider_scope(db: Connection) -> None:
    db.exec_driver_sql(
        "INSERT INTO channel_tokens (id, channel_id, token_hash, label, created_at) "
        "VALUES (gen_random_uuid(), 'canal-x', repeat('a', 64), 'mac', now())"
    )
    report = inspect_snapshot(db)
    assert report["scope"] == "bootstrap+pilots"


@pytest.mark.postgres
def test_snapshot_rejects_enabled_real_provider_before_first_request(db: Connection) -> None:
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
    with pytest.raises(ValueError, match="real_provider_enabled"):
        inspect_snapshot(db)


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
        "revision": "0015",
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


@pytest.mark.postgres
def test_encrypted_public_schema_restores_in_fresh_cluster(
    postgres_engine: Engine, tmp_path: Path
) -> None:
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
