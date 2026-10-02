from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Connection, select

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
