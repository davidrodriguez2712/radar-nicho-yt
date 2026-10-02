import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, delete, select
from sqlalchemy.dialects.postgresql import insert

from nicheradar.integrations.contracts import Batch, Operation
from nicheradar.repositories import schema_v1 as s


def cache_key(
    provider: str,
    operation: Operation,
    parameters: dict[str, Any],
    auth_scope: str,
    contract_version: str = "normalized-v1",
) -> str:
    # List ordering is preserved because it can be semantically significant.
    # Secret material must never be supplied in parameters or account scope.
    canonical = json.dumps(
        [provider, operation.value, parameters, auth_scope, contract_version],
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def cached_batch(connection: Connection, key: str, now: datetime) -> Batch | None:
    row = connection.execute(
        select(s.raw_observations.c.payload)
        .join(s.provider_cache, s.provider_cache.c.observation_id == s.raw_observations.c.id)
        .where(
            s.provider_cache.c.cache_key == key,
            s.provider_cache.c.cache_valid_until > now,
            s.raw_observations.c.retain_until > now,
        )
    ).first()
    return Batch.model_validate(row[0]) if row else None


def store_cache(
    connection: Connection, key: str, observation_id: object, valid_until: datetime
) -> None:
    statement = insert(s.provider_cache).values(
        cache_key=key, observation_id=observation_id, cache_valid_until=valid_until
    )
    connection.execute(
        statement.on_conflict_do_update(
            index_elements=["cache_key"],
            set_={"observation_id": observation_id, "cache_valid_until": valid_until},
        )
    )


def invalidate_cache(connection: Connection, key: str) -> None:
    connection.execute(delete(s.provider_cache).where(s.provider_cache.c.cache_key == key))
