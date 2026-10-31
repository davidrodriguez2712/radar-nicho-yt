# src/nicheradar/subniche_discovery/report.py
"""Read-only reports: hypothesis ranking and spend by provider/operation."""

from datetime import datetime
from typing import Any

from sqlalchemy import Connection, func, select

from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.schema import hypothesis_channel_hits as hits
from nicheradar.repositories.schema import hypothesis_snapshots as snapshots
from nicheradar.repositories.schema import niche_hypotheses as nh


def _money(value: Any) -> str | None:
    return None if value is None else f"{value:.2f}"


def ranking(connection: Connection, *, examples: int = 3) -> list[dict[str, Any]]:
    latest = (
        select(snapshots, nh.c.slug, nh.c.label, nh.c.finalist)
        .join(nh, nh.c.id == snapshots.c.hypothesis_id)
        .distinct(snapshots.c.hypothesis_id)
        .order_by(snapshots.c.hypothesis_id, snapshots.c.measured_at.desc())
    )
    rows: list[dict[str, Any]] = []
    for row in connection.execute(latest).mappings():
        sample = connection.execute(
            select(hits)
            .where(
                hits.c.hypothesis_id == row["hypothesis_id"],
                hits.c.run_id == row["run_id"],
                hits.c.excluded_reason.is_(None),
            )
            .order_by(hits.c.income_high.desc().nulls_last(), hits.c.monthly_long_views.desc())
            .limit(examples)
        ).mappings()
        profile = row["profile"]
        rows.append(
            {
                "slug": row["slug"],
                "label": row["label"],
                "finalist": row["finalist"],
                "measured_at": row["measured_at"],
                "stable_channels": row["stable_channels"],
                "traction_channels": row["traction_channels"],
                "median_income_low": _money(row["median_income_low"]),
                "median_income_high": _money(row["median_income_high"]),
                "rpm_source": profile.get("rpm_source"),
                "signal": profile.get("signal"),
                "examples": [
                    {
                        "channel_id": hit["channel_id"],
                        "monthly_long_views": hit["monthly_long_views"],
                        "income_low": _money(hit["income_low"]),
                        "income_high": _money(hit["income_high"]),
                        "traction": hit["traction"],
                        "flags": hit["flags"],
                    }
                    for hit in sample
                ],
            }
        )
    rows.sort(
        key=lambda r: (
            -r["traction_channels"],
            r["median_income_high"] is None,
            -float(r["median_income_high"] or 0),
            r["slug"],
        )
    )
    return rows


def spend_rows(connection: Connection, since: datetime) -> list[dict[str, Any]]:
    query = (
        select(
            s.provider_requests.c.provider,
            s.provider_requests.c.operation,
            s.cost_ledger.c.unit,
            func.count().label("calls"),
            func.sum(s.cost_ledger.c.amount).label("amount"),
        )
        .join(s.provider_requests, s.provider_requests.c.id == s.cost_ledger.c.request_id)
        .where(s.cost_ledger.c.occurred_at >= since)
        .group_by(
            s.provider_requests.c.provider, s.provider_requests.c.operation, s.cost_ledger.c.unit
        )
        .order_by(s.provider_requests.c.provider, s.provider_requests.c.operation)
    )
    return [
        {
            "provider": row.provider,
            "operation": row.operation,
            "unit": row.unit,
            "calls": row.calls,
            "amount": f"{row.amount:f}",
        }
        for row in connection.execute(query)
    ]
