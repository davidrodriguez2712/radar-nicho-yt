"""Settle as a US$0 charge the screenshot-reading requests whose charge stayed unknown.

Usage: release_unknown_evidence_requests.py [--apply]     (default: dry run, nothing is written)
A request left in `unknown_charge` (the provider rejected the call, e.g. an exhausted balance)
makes the gateway refuse every identical request, so that listing is skipped forever, and it keeps
its whole reservation (about US$0.105) inside the budget. Settling it as zero completes it, frees
the reservation and lets the listing be processed again. Only OpenAI `listing_evidence` requests
are touched: `unknown_charge`, or `sent` for more than 30 minutes (a run killed in flight).
"""

import json
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Engine, func, select

from nicheradar.config import Settings
from nicheradar.integrations.contracts import Operation
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.database import database_engine
from nicheradar.services.budget import settle

STALE_SENT = timedelta(minutes=30)


def release_unknown_evidence_requests(
    engine: Engine, *, apply: bool, now: datetime
) -> dict[str, object]:
    requests = s.provider_requests
    with engine.begin() as connection:
        rows = connection.execute(
            select(requests.c.id, requests.c.state, s.analysis_runs.c.profile_id)
            .join(s.analysis_runs, s.analysis_runs.c.id == requests.c.run_id)
            .where(
                requests.c.provider == "openai",
                requests.c.operation == Operation.LISTING_EVIDENCE.value,
                (requests.c.state == "unknown_charge")
                | ((requests.c.state == "sent") & (requests.c.sent_at < now - STALE_SENT)),
            )
            .order_by(requests.c.created_at)
        ).all()
        held = Decimal(0)
        for row in rows:
            held += connection.execute(
                select(func.coalesce(func.sum(s.cost_reservations.c.amount), 0)).where(
                    s.cost_reservations.c.request_id == row.id,
                    s.cost_reservations.c.status.in_(["reserved", "unknown_charge"]),
                )
            ).scalar_one()
            if apply:
                settle(connection, row.id, row.profile_id, {"USD": Decimal(0)}, now)
    return {
        "requests": len(rows),
        "unknown_charge": sum(row.state == "unknown_charge" for row in rows),
        "sent_stale": sum(row.state == "sent" for row in rows),
        "reservation_usd_freed": str(held),
    }


def main() -> None:
    apply = "--apply" in sys.argv[1:]
    result = release_unknown_evidence_requests(
        database_engine(Settings()), apply=apply, now=datetime.now(UTC)
    )
    print(json.dumps({"applied": apply, **result}))


if __name__ == "__main__":
    main()
