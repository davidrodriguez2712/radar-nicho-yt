from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Connection, select
from sqlalchemy.dialects.postgresql import insert

from nicheradar.integrations.contracts import Operation, ProviderError
from nicheradar.repositories import schema_v1 as s


class Usage(StrEnum):
    LLM_PROCESSING = "llm_processing"
    QUERY = "query"
    SCHEDULED = "scheduled"
    STORAGE = "storage"
    HISTORY = "history"
    DERIVED = "derived"


def require_usage(
    connection: Connection,
    provider: str,
    operation: Operation,
    usage: Usage,
    data_type: str,
    now: datetime,
) -> UUID | None:
    if provider == "synthetic":
        return None
    row = (
        connection.execute(
            select(s.provider_policies)
            .where(
                s.provider_policies.c.provider == provider,
                s.provider_policies.c.operation.in_([operation.value, "*"]),
                s.provider_policies.c.usage == usage.value,
                s.provider_policies.c.data_type == data_type,
                s.provider_policies.c.effective_at <= now,
            )
            .order_by(
                s.provider_policies.c.effective_at.desc(), s.provider_policies.c.created_at.desc()
            )
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None or row["status"] != "enabled":
        raise ProviderError("policy_pending" if row is None else f"policy_{row['status']}")
    return UUID(str(row["id"]))


# Explicit per-operation rows (never "*"): each YouTube Data API operation the radar calls
# is attested individually against the developer policies. Values are Operation enum
# values, which is what require_usage() matches on.
YOUTUBE_POLICY_OPERATIONS = (
    Operation.VIDEOS,
    Operation.CHANNELS,
    Operation.UPLOADS,
    Operation.SEARCH,
    Operation.COMMENT_THREADS,
    Operation.VIDEO_CATEGORIES,
)
YOUTUBE_POLICY_VERSION = "youtube-developer-policies-2026-09-23"
YOUTUBE_POLICY_EVIDENCE = "https://developers.google.com/youtube/terms/developer-policies"


def seed_youtube_policies(connection: Connection, now: datetime, *, llm_enabled: bool) -> None:
    """Idempotently enable YouTube metadata usages for live activation."""
    usages: tuple[str, ...] = ("query", "storage", "history", "derived", "scheduled")
    if llm_enabled:
        usages = (*usages, "llm_processing")
    for operation in YOUTUBE_POLICY_OPERATIONS:
        for usage in usages:
            statement = insert(s.provider_policies).values(
                provider="youtube",
                operation=operation.value,
                data_type="metadata",
                usage=usage,
                version=YOUTUBE_POLICY_VERSION,
                status="enabled",
                evidence_source=YOUTUBE_POLICY_EVIDENCE,
                retention_seconds=7 * 86400,
                effective_at=now,
            )
            connection.execute(
                statement.on_conflict_do_update(
                    index_elements=["provider", "data_type", "operation", "usage", "version"],
                    set_={
                        "status": "enabled",
                        "evidence_source": YOUTUBE_POLICY_EVIDENCE,
                        "retention_seconds": 7 * 86400,
                        "effective_at": now,
                    },
                )
            )
