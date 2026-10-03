"""Read-only: dump one saved channel-analysis snapshot's stage-by-stage status."""

import json
import sys

from sqlalchemy import select

from nicheradar.config import Settings
from nicheradar.repositories.database import database_engine
from nicheradar.repositories.schema import channel_analyses

analysis_id = sys.argv[1]
engine = database_engine(Settings())
with engine.connect() as connection:
    row = (
        connection.execute(select(channel_analyses).where(channel_analyses.c.id == analysis_id))
        .mappings()
        .one()
    )

snapshot = row["snapshot"] or {}
stages = {}
for stage, data in snapshot.items():
    if isinstance(data, dict):
        stages[stage] = {
            "keys": sorted(data.keys()),
            "reason": data.get("reason"),
            "status": data.get("status"),
        }
    else:
        stages[stage] = {"type": type(data).__name__}

print(
    json.dumps(
        {
            "status": row["status"],
            "channel_input": row["channel_input"],
            "channel_external_id": row["channel_external_id"],
            "consumption": row["consumption"],
            "stages": stages,
            "metrics": snapshot.get("metrics"),
        },
        default=str,
    )
)
