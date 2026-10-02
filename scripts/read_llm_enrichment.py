"""Emit aggregate LLM enrichment outcomes for the latest run; no provider payloads."""

import json
from collections import Counter

from sqlalchemy import select

from nicheradar.config import Settings
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.database import database_engine

engine = database_engine(Settings())
with engine.connect() as connection:
    rows = (
        connection.execute(
            select(s.evaluation_versions.c.explanation)
            .join(s.analysis_runs, s.analysis_runs.c.id == s.evaluation_versions.c.run_id)
            .order_by(s.evaluation_versions.c.created_at.desc())
            .limit(30)
        )
        .scalars()
        .all()
    )
    outcomes = Counter()
    for explanation in rows:
        narrative = (explanation or {}).get("narrative") or {}
        outcomes[narrative.get("enrichment", "missing")] += 1
    requests = (
        connection.execute(
            select(s.provider_requests.c.state, s.provider_requests.c.error_code)
            .where(s.provider_requests.c.provider == "openai")
            .order_by(s.provider_requests.c.created_at.desc())
            .limit(20)
        )
        .mappings()
        .all()
    )
    request_states = Counter((row["state"], row["error_code"]) for row in requests)
print(
    json.dumps(
        {
            "narrative_enrichment_outcomes": dict(outcomes),
            "openai_request_states": {str(key): value for key, value in request_states.items()},
        }
    )
)
