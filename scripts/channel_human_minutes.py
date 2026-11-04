#!/usr/bin/env python3
"""Calcula los minutos humanos por video y convierte el outbox de un canal a channel-report-v3.

Solo biblioteca estándar. Lee en solo lectura los registros de sesión de Claude Code de la
carpeta del canal y ``datos/pipeline.db``; nunca guarda ni imprime el texto de las conversaciones.
Ver docs/contracts/channel-report-v3.md.
"""

import json
import math
import re
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
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
