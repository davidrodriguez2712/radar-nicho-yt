#!/usr/bin/env python3
"""Calcula los minutos humanos por video y convierte el outbox de un canal a channel-report-v3.

Solo biblioteca estándar. Lee en solo lectura los registros de sesión de Claude Code de la
carpeta del canal y ``datos/pipeline.db``; nunca guarda ni imprime el texto de las conversaciones.
Ver docs/contracts/channel-report-v3.md.
"""

import argparse
import json
import math
import os
import re
import sqlite3
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

METHOD = "claude_sessions_plus_assumed"
CAP_SECONDS = 15 * 60
ASSUMED_MINUTES = 10
MAX_MINUTES = 100_000


class HumanMinutesError(Exception):
    """Error esperado al calcular minutos humanos; el mensaje está en español."""


@dataclass(frozen=True)
class HumanPrompt:
    at: datetime
    gap_seconds: float


def _moment(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except (ValueError, OverflowError):
        return None


def is_human_prompt(record: Mapping[str, object]) -> bool:
    if record.get("type") != "user" or record.get("isMeta") or record.get("isSidechain"):
        return False
    if record.get("toolUseResult") is not None:
        return False
    message = record.get("message")
    content = message.get("content") if isinstance(message, Mapping) else None
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        kinds = [block.get("type") for block in content if isinstance(block, Mapping)]
        return "text" in kinds and "tool_result" not in kinds
    return False


def session_dirs(channel_dir: Path, homes: Sequence[Path]) -> list[Path]:
    encoded = re.sub(r"[^A-Za-z0-9-]", "-", str(channel_dir.resolve()))
    found = [home / "projects" / encoded for home in homes]
    return [path for path in found if path.is_dir()]


def read_human_prompts(files: Iterable[Path], cap_seconds: float) -> list[HumanPrompt]:
    prompts: list[HumanPrompt] = []
    for path in files:
        last: dict[str, datetime] = {}
        try:
            handle = path.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with handle:
            _scan(handle, last, prompts, cap_seconds)
    return sorted(prompts, key=lambda prompt: prompt.at)


def _scan(
    lines: Iterable[str], last: dict[str, datetime], prompts: list[HumanPrompt], cap_seconds: float
) -> None:
    try:
        for line in lines:
            try:
                record = json.loads(line)
            except (ValueError, RecursionError):
                continue
            if not isinstance(record, dict):
                continue
            at = _moment(record.get("timestamp"))
            session = record.get("sessionId")
            if at is None or not isinstance(session, str):
                continue
            if record.get("type") in ("user", "assistant") and is_human_prompt(record):
                previous = last.get(session)
                gap = 0.0 if previous is None else (at - previous).total_seconds()
                prompts.append(HumanPrompt(at, min(max(gap, 0.0), cap_seconds)))
            if record.get("type") in ("user", "assistant", "system"):
                last[session] = at
    except OSError:
        return


def read_windows(db_path: Path) -> dict[str, tuple[datetime, datetime]]:
    """Ventana de producción por video: primer evento hasta PROGRAMADO/PUBLICADO (o el último)."""
    if not db_path.is_file():
        raise HumanMinutesError(f"No se encontró la base del canal: {db_path}")
    uri = f"file:{quote(str(db_path.resolve()))}?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True)
        try:
            rows = con.execute(
                "SELECT video_id, a_estado, creado_en FROM eventos ORDER BY id"
            ).fetchall()
        finally:
            con.close()
    except sqlite3.Error as error:
        raise HumanMinutesError(
            f"No se pudo leer la tabla 'eventos' de la base del canal: {error}"
        ) from error
    events: dict[str, list[tuple[datetime, object]]] = {}
    for video, state, created in rows:
        at = _moment(created)
        if at is None or not isinstance(video, str):
            continue
        events.setdefault(video, []).append((at, state))
    windows: dict[str, tuple[datetime, datetime]] = {}
    for video, items in events.items():
        items.sort(key=lambda item: item[0])
        end = next(
            (at for at, state in items if state in ("PROGRAMADO", "PUBLICADO")), items[-1][0]
        )
        windows[video] = (items[0][0], end)
    return windows


@dataclass(frozen=True)
class Attribution:
    by_video: dict[str, float]
    unattributed: float
    total: float
    known: frozenset[str]


def attribute(
    prompts: Sequence[HumanPrompt], windows: Mapping[str, tuple[datetime, datetime]]
) -> Attribution:
    """Reparte los segundos de cada mensaje entre los videos cuya ventana lo contiene."""
    parts: dict[str, list[float]] = {}
    lost: list[float] = []
    for prompt in prompts:
        inside = [v for v, (start, end) in windows.items() if start <= prompt.at <= end]
        if not inside:
            lost.append(prompt.gap_seconds)
            continue
        share = prompt.gap_seconds / len(inside)
        for video in inside:
            parts.setdefault(video, []).append(share)
    by_video = {video: math.fsum(values) for video, values in parts.items()}
    unattributed = math.fsum(lost)
    total = math.fsum([*by_video.values(), unattributed])
    return Attribution(by_video, unattributed, total, frozenset(windows))


def video_minutes(
    attribution: Attribution, video_id: str, published: bool, assumed: int
) -> tuple[int, int] | None:
    """(medidos, supuestos) del video, o None si no se conoce; nunca inventa 0."""
    if assumed < 0:
        raise ValueError("Los minutos supuestos no pueden ser negativos.")
    if video_id not in attribution.known:
        return None
    measured = min(math.ceil(attribution.by_video.get(video_id, 0.0) / 60), MAX_MINUTES)
    applied = min(assumed if published else 0, MAX_MINUTES - measured)
    return measured, applied


@dataclass(frozen=True)
class Summary:
    """(video_id, human_minutes, medidos, supuestos) por video convertido."""

    lines: tuple[tuple[str, int | None, int, int], ...]


def convert_report(
    payload: Mapping[str, object], attribution: Attribution, assumed: int
) -> tuple[dict[str, object], Summary] | None:
    """Convierte un reporte v1/v2 a v3; None si no es convertible. Lo demás queda idéntico."""
    contract = payload.get("contract")
    if contract not in ("channel-report-v1", "channel-report-v2"):
        return None
    videos = payload.get("videos")
    if not isinstance(videos, list) or not all(isinstance(v, Mapping) for v in videos):
        return None
    converted: dict[str, object] = {}
    for key, value in payload.items():
        if key == "contract":
            converted[key] = "channel-report-v3"
        else:
            converted[key] = value  # "videos" se sustituye abajo conservando su posición
    converted["format"] = "long" if contract == "channel-report-v1" else "shorts"
    converted["human_minutes_method"] = METHOD
    lines: list[tuple[str, int | None, int, int]] = []
    new_videos: list[dict[str, object]] = []
    for video in videos:
        item = dict(video)
        video_id = str(item.get("video_id", ""))
        published = item.get("published_at") is not None
        result = video_minutes(attribution, video_id, published, assumed) if published else None
        if result is None:
            item["human_minutes"] = None
            lines.append((video_id, None, 0, 0))
        else:
            item["human_minutes"] = result[0] + result[1]
            lines.append((video_id, result[0] + result[1], result[0], result[1]))
        new_videos.append(item)
    converted["videos"] = new_videos
    return converted, Summary(tuple(lines))


def _write_bytes_atomic(path: Path, data: bytes, mode: int | None = None) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        tmp.write_bytes(data)
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _write_atomic(path: Path, payload: Mapping[str, object]) -> None:
    mode = path.stat().st_mode & 0o7777 if path.exists() else None
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    _write_bytes_atomic(path, text.encode("utf-8"), mode)


def convert_outbox(
    channel_dir: Path,
    attribution: Attribution,
    assumed: int,
    out: Callable[[str], None],
    dry_run: bool = False,
) -> int:
    outbox = channel_dir / ".nicheradar" / "outbox"
    files = sorted(outbox.glob("*.json")) if outbox.is_dir() else []
    failures = converted_count = skipped = 0
    for path in files:
        try:
            payload = json.loads(path.read_text("utf-8"))
        except (ValueError, OSError, RecursionError):
            out(f"{path.name}: no es JSON válido; se deja intacto")
            failures += 1
            continue
        if isinstance(payload, dict) and payload.get("contract") == "channel-report-v3":
            out(f"{path.name}: ya es channel-report-v3; se omite")
            skipped += 1
            continue
        result = (
            convert_report(payload, attribution, assumed) if isinstance(payload, dict) else None
        )
        if result is None:
            out(f"{path.name}: no es un reporte v1/v2 convertible; se deja intacto")
            failures += 1
            continue
        report, summary = result
        if not dry_run:
            backup = path.with_name(path.name + ".orig")
            try:
                if path.is_symlink() or backup.is_symlink():
                    raise OSError(0, "es un enlace simbólico")
                if not backup.exists():
                    _write_bytes_atomic(backup, path.read_bytes())
                _write_atomic(path, report)
            except OSError as error:
                out(f"{path.name}: no se pudo escribir ({error.strerror}); se deja intacto")
                failures += 1
                continue
        converted_count += 1
        out(f"{path.name}: {'se convertiría' if dry_run else 'convertido'} a channel-report-v3")
        for video_id, minutes, measured, assumed_part in summary.lines:
            if minutes is None:
                out(f"  {video_id}: sin dato (null)")
            else:
                out(f"  {video_id}: medido {measured} · supuesto {assumed_part} = {minutes} min")
    out(f"archivos convertidos: {converted_count} · omitidos: {skipped} · fallidos: {failures}")
    return 1 if failures else 0


def _non_negative(text: str) -> int:
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("debe ser un entero >= 0")
    return value


def _positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("debe ser un entero >= 1")
    return value


def main(argv: Sequence[str] | None = None, homes: Sequence[Path] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel-dir", type=Path, required=True)
    parser.add_argument("--assumed-minutes", type=_non_negative, default=ASSUMED_MINUTES)
    parser.add_argument("--cap-minutes", type=_positive, default=CAP_SECONDS // 60)
    parser.add_argument("--sessions-home", type=Path, action="append")
    parser.add_argument("--sessions-dir", type=Path, action="append")
    parser.add_argument("--db", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    channel_dir: Path = args.channel_dir
    if homes is None:
        homes = args.sessions_home or [Path.home() / ".claude", Path.home() / ".claude-alt"]
    dirs: list[Path] = args.sessions_dir or session_dirs(channel_dir, list(homes))
    files = sorted(file for folder in dirs for file in folder.glob("*.jsonl"))
    db_path: Path = args.db or channel_dir / "datos" / "pipeline.db"
    try:
        windows = read_windows(db_path)
    except HumanMinutesError as error:
        print(str(error))
        return 1
    prompts = read_human_prompts(files, args.cap_minutes * 60)
    attribution = attribute(prompts, windows)
    print(f"carpetas de sesiones: {len(dirs)} · archivos: {len(files)} · mensajes: {len(prompts)}")
    print(f"minutos humanos medidos totales: {attribution.total / 60:.1f}")
    share = attribution.unattributed / attribution.total if attribution.total > 0 else 0.0
    print(f"minutos sin atribuir: {attribution.unattributed / 60:.1f} ({share * 100:.0f} %)")
    if share > 0.6:
        print(
            "Aviso: más del 60 % del tiempo humano medido cae fuera de las ventanas de "
            "producción de los videos; las cifras por video subestiman el tiempo medido."
        )
    return convert_outbox(channel_dir, attribution, args.assumed_minutes, print, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
