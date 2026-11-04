#!/usr/bin/env python3
"""Calcula los minutos humanos por video y convierte el outbox de un canal a channel-report-v3.

Solo biblioteca estándar. Lee en solo lectura los registros de sesión de Claude Code de la
carpeta del canal y ``datos/pipeline.db``; nunca guarda ni imprime el texto de las conversaciones.
Ver docs/contracts/channel-report-v3.md.
"""

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

METHOD = "claude_sessions_plus_assumed"
CAP_SECONDS = 15 * 60
ASSUMED_MINUTES = 10
MAX_MINUTES = 100_000


@dataclass(frozen=True)
class HumanPrompt:
    at: datetime
    gap_seconds: float


def _moment(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


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
            lines = path.read_text("utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                record = json.loads(line)
            except ValueError:
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
    return sorted(prompts, key=lambda prompt: prompt.at)
