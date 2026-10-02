"""Read-only ranking snapshot: scores, evidence volume and market blockers per opportunity."""

import json

from sqlalchemy import select

from nicheradar.config import Settings
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.database import database_engine

engine = database_engine(Settings())
with engine.connect() as connection:
    rows = (
        connection.execute(
            select(
                s.opportunities.c.id,
                s.opportunities.c.audience_key,
                s.opportunities.c.format,
                s.opportunities.c.language,
                s.topics.c.label,
                s.cohorts.c.coverage,
                s.evaluation_versions.c.state,
                s.evaluation_versions.c.confidence,
                s.evaluation_versions.c.market_score,
                s.evaluation_versions.c.creator_fit,
                s.evaluation_versions.c.final_score,
                s.evaluation_versions.c.explanation,
                s.evaluation_versions.c.created_at,
            )
            .select_from(s.evaluation_versions)
            .join(s.opportunities, s.opportunities.c.id == s.evaluation_versions.c.opportunity_id)
            .join(s.cohorts, s.cohorts.c.id == s.evaluation_versions.c.cohort_id)
            .join(s.topics, s.topics.c.id == s.cohorts.c.topic_id)
            .where(s.evaluation_versions.c.expired_at.is_(None))
            .order_by(s.evaluation_versions.c.created_at.desc())
        )
        .mappings()
        .all()
    )
    latest_by_opportunity: dict[str, dict] = {}
    for row in rows:
        key = str(row["id"])
        if key not in latest_by_opportunity:
            latest_by_opportunity[key] = dict(row)

items = []
for row in latest_by_opportunity.values():
    explanation = row["explanation"] or {}
    market = explanation.get("market") or {}
    metrics = explanation.get("metrics") or {}
    items.append(
        {
            "opportunity_id": str(row["id"]),
            "audience_key": row["audience_key"],
            "format": row["format"],
            "language": row["language"],
            "topic_label": row["label"],
            "cohort_videos": (row["coverage"] or {}).get("included"),
            "market_state": row["state"],
            "confidence": row["confidence"],
            "market_score": row["market_score"],
            "creator_fit": row["creator_fit"],
            "final_score": row["final_score"],
            "market_missing": market.get("missing"),
            "market_components": market.get("components"),
            "videos_in_cohort": metrics.get("videos"),
            "channels_in_cohort": metrics.get("channels"),
            "breakout_rate": metrics.get("breakout_rate"),
            "concentration_score": metrics.get("concentration_score"),
        }
    )

items.sort(
    key=lambda item: (
        item["final_score"] is not None,
        item["market_score"] is not None,
        item["videos_in_cohort"] or 0,
        item["creator_fit"] or 0,
    ),
    reverse=True,
)
print(json.dumps(items[:10], default=str))
