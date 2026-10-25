"""Emit counts of flow-research requests and dossiers by status; no content or evidence."""

import json

from sqlalchemy import text

from nicheradar.config import Settings
from nicheradar.repositories.database import database_engine

engine = database_engine(Settings())
with engine.connect() as connection:
    connection.execute(text("SET TRANSACTION READ ONLY"))
    requests = connection.execute(
        text("SELECT status, count(*) FROM flow_research_requests GROUP BY status")
    ).all()
    dossiers = connection.execute(text("SELECT count(*) FROM flow_research_dossiers")).scalar_one()
    revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
print(
    json.dumps(
        {
            "revision": revision,
            "requests_by_status": {status: int(count) for status, count in requests},
            "dossiers": int(dossiers),
        }
    )
)
