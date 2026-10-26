"""Manual encrypted backup (bootstrap, pilots, market and flow research) and restore drill.

No provider-evidence export, scheduler, cloud upload, or writes to the source VPS.
`prune` applies the local retention policy (docs/backup-restore.md); dry-run by default.
Run with uv run python scripts/backup_mac.py --help. Secrets never go in argv.
"""

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import selectors
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path.home() / "Library/Application Support/NicheRadar"
SSH = [
    "ssh",
    "-i",
    str(Path.home() / ".ssh/id_ed25519"),
    "-o",
    "IdentitiesOnly=yes",
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=10",
    "-o",
    "StrictHostKeyChecking=yes",
    "root@194.61.28.253",
]
PREFIX = "proy1-credito-riesgo_nicheradar-"
MAX_BYTES = 32 * 1024 * 1024
SCOPES = (
    "bootstrap-only",
    "bootstrap+pilots",
    "bootstrap+research",
    "bootstrap+pilots+research",
)
# Local retention: newest copy of each of the last 7 days with copies, plus the newest copy of
# each of the 4 previous ISO weeks. A copy is also destroyed at its data deadline (`delete_after`).
DAILY_KEEP = 7
WEEKLY_KEEP = 4
ARCHIVE_NAME = re.compile(r"bootstrap-(\d{8}T\d{6}Z)-[0-9a-f]{8}\.gpg")


def private_path(path: Path, *, directory: bool) -> None:
    info = path.lstat()
    valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not valid or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError("private_owner_only_path_required")


def initialize(root: Path) -> None:
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    private_path(root, directory=True)
    for name in ("backups", "keys"):
        (root / name).mkdir(mode=0o700, exist_ok=True)
        private_path(root / name, directory=True)
    key = root / "keys/backup.key"
    if not key.exists():
        # Exclusive creation: never replace a key that protects existing backups.
        with open(key, "x", opener=lambda path, flags: os.open(path, flags, 0o600)) as file:
            file.write(secrets.token_urlsafe(48) + "\n")
            file.flush()
            os.fsync(file.fileno())
    private_path(key, directory=False)


def crypt(data: bytes, key: Path, *, decrypt: bool = False) -> bytes:
    private_path(key.parent, directory=True)
    private_path(key, directory=False)
    binary = shutil.which("gpg")
    if not binary:
        raise ValueError("gpg_required")
    with tempfile.TemporaryDirectory(prefix="nrgpg-") as home:
        result = subprocess.run(
            [
                binary,
                "--no-options",
                "--homedir",
                home,
                "--batch",
                "--no-tty",
                "--pinentry-mode",
                "loopback",
                "--no-symkey-cache",
                "--passphrase-file",
                str(key),
                "--output",
                "-",
                *(
                    ["--decrypt"]
                    if decrypt
                    else ["--symmetric", "--cipher-algo", "AES256", "--compress-algo", "none"]
                ),
            ],
            input=data,
            capture_output=True,
            timeout=60,
        )
    if result.returncode:
        raise ValueError("backup_decryption_failed" if decrypt else "backup_encryption_failed")
    return result.stdout


def ssh(arguments: list[str], *, timeout: int = 30) -> bytes:
    result = subprocess.run(
        [*SSH, shlex.join(arguments)],
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode:
        raise ValueError("scoped_ssh_command_failed")
    return result.stdout


def container(service: str) -> tuple[str, dict[str, object]]:
    ids = (
        ssh(
            [
                "docker",
                "ps",
                "--filter",
                f"label=com.docker.swarm.service.name={PREFIX}{service}",
                "--format",
                "{{.ID}}",
            ]
        )
        .decode()
        .split()
    )
    if len(ids) != 1 or not re.fullmatch(r"[a-f0-9]{12,64}", ids[0]):
        raise ValueError("expected_one_owned_container")
    # Full inspect stays in memory. Return only allowlisted metadata, never its environment.
    config = json.loads(ssh(["docker", "inspect", ids[0]]))[0]
    env = dict(item.split("=", 1) for item in config["Config"]["Env"] if "=" in item)
    if service in {"api", "worker"}:
        # Live mode is allowed (decision 2026-10-26): what protects provider evidence is the
        # data guard in backup_snapshot (unreviewed tables with rows fail closed) plus the pause.
        if env.get("NR_MODE") not in {"synthetic", "live"} or env.get("NR_RADAR_PAUSED") != "true":
            raise ValueError("unsafe_runtime")
    elif env.get("POSTGRES_DB") != "nicheradar":
        raise ValueError("unexpected_database")
    if config["HostConfig"]["PortBindings"]:
        raise ValueError("unexpected_published_ports")
    return ids[0], {"image": config["Config"]["Image"], "image_id": config["Image"]}


def take_snapshot() -> tuple[dict[str, object], bytes]:
    api, api_meta = container("api")
    _, worker_meta = container("worker")
    database, db_meta = container("db")
    source = Path(__file__).with_name("backup_snapshot.py").read_text()
    holder = subprocess.Popen(
        [*SSH, shlex.join(["docker", "exec", "-i", api, "python", "-c", source])],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert holder.stdout is not None and holder.stdin is not None
        with selectors.DefaultSelector() as selector:
            selector.register(holder.stdout, selectors.EVENT_READ)
            if not selector.select(timeout=35):
                raise ValueError("snapshot_guard_timeout")
        report = json.loads(holder.stdout.readline(16384))
        snapshot = report.pop("snapshot")
        if not re.fullmatch(r"[A-Fa-f0-9]+-[A-Fa-f0-9]+-[0-9]+", snapshot):
            raise ValueError("invalid_snapshot")
        dump = ssh(
            [
                "docker",
                "exec",
                database,
                "pg_dump",
                "--username=postgres",
                "--dbname=nicheradar",
                "--format=custom",
                "--no-owner",
                "--no-acl",
                "--schema=public",
                f"--snapshot={snapshot}",
            ],
            timeout=90,
        )
        if len(dump) > MAX_BYTES or not dump.startswith(b"PGDMP"):
            raise ValueError("unexpected_dump")
        holder.stdin.write(b"release\n")
        holder.stdin.flush()
        holder.stdin.close()
        if holder.wait(timeout=15) != 0:
            raise ValueError("snapshot_guard_failed")
        report.update(
            created_at=datetime.now(UTC).isoformat(),
            source="contabo/proy1-credito-riesgo/nicheradar-db",
            images={"api": api_meta, "worker": worker_meta, "db": db_meta},
            dump_sha256=hashlib.sha256(dump).hexdigest(),
        )
        return report, dump
    finally:
        if holder.stdin:
            holder.stdin.close()
        if holder.poll() is None:
            holder.terminate()
            holder.wait(timeout=15)
        if holder.stdout:
            holder.stdout.close()


def save_backup(
    root: Path, report: dict[str, object], dump: bytes, *, now: datetime | None = None
) -> Path:
    private_path(root, directory=True)
    private_path(root / "backups", directory=True)
    payload = json.dumps({"metadata": report, "dump": base64.b64encode(dump).decode()}).encode()
    encrypted = crypt(payload, root / "keys/backup.key")
    # Finish authentication/decryption before declaring the archive usable.
    if crypt(encrypted, root / "keys/backup.key", decrypt=True) != payload:
        raise ValueError("encrypted_roundtrip_failed")
    filename = f"bootstrap-{now or datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}.gpg"
    archive = root / "backups" / filename
    with open(archive, "xb", opener=lambda path, flags: os.open(path, flags, 0o600)) as file:
        file.write(encrypted)
        file.flush()
        os.fsync(file.fileno())
    return archive


def load_backup(root: Path, archive: Path) -> tuple[dict[str, object], bytes]:
    private_path(archive, directory=False)
    if archive.stat().st_size > 2 * MAX_BYTES:
        raise ValueError("archive_too_large")
    data = json.loads(crypt(archive.read_bytes(), root / "keys/backup.key", decrypt=True))
    dump = base64.b64decode(data["dump"], validate=True)
    report = data["metadata"]
    if (
        report.get("scope") not in SCOPES
        or report.get("revision") != "0016"
        or hashlib.sha256(dump).hexdigest() != report.get("dump_sha256")
        or not dump.startswith(b"PGDMP")
    ):
        raise ValueError("invalid_archive")
    return report, dump


def plan_retention(
    archives: list[tuple[str, datetime, datetime | None]], now: datetime
) -> dict[str, str]:
    """Pure policy: name -> keep:daily | keep:weekly | delete:expired | delete:superseded."""
    verdicts: dict[str, str] = {}
    live: list[tuple[str, datetime]] = []
    for name, created, delete_after in sorted(archives, key=lambda item: item[1], reverse=True):
        if delete_after is not None and delete_after <= now:
            verdicts[name] = "delete:expired"
        else:
            live.append((name, created))
    days: set[object] = set()
    weeks: set[object] = set()
    for name, created in live:  # newest first
        day = created.date()
        week = created.isocalendar()[:2]
        if day in days:
            verdicts[name] = "delete:superseded"
        elif len(days) < DAILY_KEEP:
            days.add(day)
            verdicts[name] = "keep:daily"
        elif week not in weeks and len(weeks) < WEEKLY_KEEP:
            weeks.add(week)
            verdicts[name] = "keep:weekly"
        else:
            verdicts[name] = "delete:superseded"
    return verdicts


def prune_backups(root: Path, now: datetime, *, apply: bool) -> dict[str, object]:
    """Delete only expired/superseded LOCAL archives of this tool; never touches anything else.

    Candidates must be plain files (no symlinks) owned by this user, directly inside
    `backups/`, with this tool's exact name pattern. Unreadable archives are kept and reported.
    """
    private_path(root, directory=True)
    backups = root / "backups"
    private_path(backups, directory=True)
    entries: list[tuple[str, datetime, datetime | None]] = []
    paths: dict[str, Path] = {}
    unsafe: list[str] = []
    unreadable: list[str] = []
    for path in sorted(backups.iterdir()):
        match = ARCHIVE_NAME.fullmatch(path.name)
        if not match:
            continue
        try:
            private_path(path, directory=False)
        except (ValueError, OSError):
            unsafe.append(path.name)
            continue
        try:
            payload = json.loads(crypt(path.read_bytes(), root / "keys/backup.key", decrypt=True))
            raw = payload["metadata"].get("delete_after")
            delete_after = datetime.fromisoformat(raw) if raw else None
        except (ValueError, KeyError, TypeError, AttributeError):
            unreadable.append(path.name)
            continue
        created = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        entries.append((path.name, created, delete_after))
        paths[path.name] = path
    plan = plan_retention(entries, now)
    doomed = sorted(name for name, verdict in plan.items() if verdict.startswith("delete"))
    deleted: list[str] = []
    if apply:
        for name in doomed:
            paths[name].unlink()
            deleted.append(name)
    return {
        "applied": apply,
        "kept": sorted(name for name, verdict in plan.items() if verdict.startswith("keep")),
        "would_delete": doomed,
        "deleted": deleted,
        "skipped_unsafe": unsafe,
        "unreadable_kept": unreadable,
    }


def restore_drill(report: dict[str, object], dump: bytes, binaries: Path) -> dict[str, object]:
    """New socket-only cluster; no input URL, ports, providers or existing DB targets."""
    from sqlalchemy import create_engine, select
    from sqlalchemy.engine import URL

    from nicheradar.repositories import schema_v1 as s
    from nicheradar.services.recovery import prepare_restore
    from scripts.backup_snapshot import inspect_snapshot

    environment = {k: v for k, v in os.environ.items() if not k.startswith(("PG", "NR_"))}
    with tempfile.TemporaryDirectory(prefix="nrrestore-", dir="/private/tmp") as temporary:
        directory = Path(temporary)
        started = False

        def run(name: str, arguments: list[str], data: bytes | None = None) -> None:
            result = subprocess.run(
                [str(binaries / name), *arguments],
                env=environment,
                input=data,
                capture_output=True,
                timeout=90,
            )
            if result.returncode:
                raise ValueError(f"isolated_{name}_failed")

        try:
            run(
                "initdb",
                [
                    "-D",
                    str(directory / "data"),
                    "-U",
                    "nicheradar_restore",
                    "--auth-local=trust",
                    "--auth-host=reject",
                    "--encoding=UTF8",
                    "--no-locale",
                ],
            )
            run(
                "pg_ctl",
                [
                    "-D",
                    str(directory / "data"),
                    "-l",
                    str(directory / "postgres.log"),
                    "-o",
                    f"-k {directory} -h '' -p 55438 -c max_connections=10",
                    "-w",
                    "start",
                ],
            )
            started = True
            environment.update(PGHOST=temporary, PGPORT="55438", PGUSER="nicheradar_restore")
            # Only the freshly initialized cluster above. No CASCADE: refuse surprises.
            # pg_dump --schema=public includes CREATE SCHEMA, unlike schema-only test fixtures.
            run(
                "psql",
                [
                    "-X",
                    "--dbname=postgres",
                    "--set=ON_ERROR_STOP=1",
                    "--command=DROP SCHEMA public",
                ],
            )
            run(
                "pg_restore",
                ["--dbname=postgres", "--no-owner", "--no-acl", "--exit-on-error"],
                dump,
            )
            url = URL.create(
                "postgresql+psycopg",
                username="nicheradar_restore",
                database="postgres",
                query={"host": temporary, "port": "55438"},
            )
            engine = create_engine(url, hide_parameters=True)
            try:
                with engine.begin() as connection:
                    restored = inspect_snapshot(connection)
                    if restored["counts"] != report["counts"]:
                        raise ValueError("restored_counts_differ")
                    profiles_before = (
                        connection.execute(select(s.creator_profiles)).mappings().all()
                    )
                    recovery = prepare_restore(connection, datetime.now(UTC))
                    for before in profiles_before:
                        after = (
                            connection.execute(
                                select(s.creator_profiles).where(
                                    s.creator_profiles.c.id == before["id"]
                                )
                            )
                            .mappings()
                            .one()
                        )
                        if after["configuration"] != before["configuration"] | {
                            "paid_limits_confirmed": False
                        }:
                            raise ValueError("restored_configuration_differ")
                    inspect_snapshot(connection)
                return {
                    "restore_verified": True,
                    "source_untouched": True,
                    "temporary_cluster_only": True,
                    "revision": restored["revision"],
                    "recovery": recovery,
                }
            finally:
                engine.dispose()
        finally:
            if started:
                run("pg_ctl", ["-D", str(directory / "data"), "-m", "fast", "-w", "stop"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "backup", "verify", "restore-drill", "prune"])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--archive", type=Path)
    parser.add_argument(
        "--apply", action="store_true", help="prune: really delete (default is a dry run)"
    )
    parser.add_argument(
        "--postgres-bin",
        type=Path,
        default=Path("/Applications/Postgres.app/Contents/Versions/latest/bin"),
    )
    args = parser.parse_args()
    if args.action == "init":
        initialize(args.root)
        print(json.dumps({"initialized": True, "root": str(args.root), "key_printed": False}))
    elif args.action == "backup":
        report, dump = take_snapshot()
        archive = save_backup(args.root, report, dump)
        print(
            json.dumps(
                {
                    "archive": str(archive),
                    "scope": report["scope"],
                    "revision": report["revision"],
                    "encrypted_bytes": archive.stat().st_size,
                }
            )
        )
    elif args.action == "prune":
        print(json.dumps(prune_backups(args.root, datetime.now(UTC), apply=args.apply)))
    else:
        if args.archive is None:
            parser.error("--archive required")
        report, dump = load_backup(args.root, args.archive)
        if args.action == "restore-drill":
            print(json.dumps(restore_drill(report, dump, args.postgres_bin)))
        else:
            print(
                json.dumps(
                    {
                        "verified": True,
                        "scope": report["scope"],
                        "revision": report["revision"],
                        "created_at": report["created_at"],
                    }
                )
            )


if __name__ == "__main__":
    # Permit the same imports when invoked as a script or in tests.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        main()
    except Exception as error:
        print(
            json.dumps(
                {
                    "backup_failed": type(error).__name__,
                    "timeout_seconds": error.timeout
                    if isinstance(error, subprocess.TimeoutExpired)
                    else None,
                    "details_withheld": True,
                }
            ),
            file=sys.stderr,
        )
        sys.exit(1)
