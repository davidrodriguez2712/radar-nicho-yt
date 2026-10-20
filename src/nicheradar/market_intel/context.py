# src/nicheradar/market_intel/context.py
"""Everything a scrape stage needs; stages never reach for globals."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Engine

from nicheradar.config import Settings
from nicheradar.integrations.llm import OpenAISelector
from nicheradar.market_intel.sources.base import ListingSource


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class RunContext:
    engine: Engine
    config: Settings
    source: ListingSource
    run_id: UUID
    analysis_run: dict[str, Any]  # {"id", "profile_id", "mode"}: needed by reserve()/settle()
    owner: str
    started_at: datetime
    checkpoints: dict[str, Any] = field(default_factory=dict)
    selector: OpenAISelector | None = None
    clock: Callable[[], datetime] = utcnow
