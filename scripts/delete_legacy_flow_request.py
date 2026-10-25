"""Delete the flow-research requests that migration 0016 rejected for lacking a language.

Owner-approved one-off cleanup. Refuses unless exactly the expected number of rows match
(rejected, language 'unknown', no dossier, no pilot) and prints only counts.
"""

import json
import sys

from sqlalchemy import text

from nicheradar.config import Settings
from nicheradar.repositories.database import database_engine

expected = int(sys.argv[1])
MATCH = (
    "status = 'rechazado' AND language = 'unknown' "
    "AND NOT EXISTS (SELECT 1 FROM flow_research_dossiers d WHERE d.request_id = r.id)"
)
engine = database_engine(Settings())
with engine.begin() as connection:
    found = connection.execute(
        text(f"SELECT count(*) FROM flow_research_requests r WHERE {MATCH}")
    ).scalar_one()
    if found != expected:
        raise SystemExit(f"expected {expected} matching requests, found {found}; nothing deleted")
    deleted = connection.execute(
        text(f"DELETE FROM flow_research_requests r WHERE {MATCH}")
    ).rowcount
    remaining = connection.execute(text("SELECT count(*) FROM flow_research_requests")).scalar_one()
print(json.dumps({"deleted": deleted, "remaining_requests": int(remaining)}))
