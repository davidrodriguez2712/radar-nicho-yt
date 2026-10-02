"""Read-only P90 demand/trend references computed from real (non-synthetic) evidence only.

Never fabricates a benchmark: an age band or trend below MINIMUM_SAMPLES stays absent,
matching the project's anti-fabrication rule (unknown, not zero or guessed).
"""

import json
import statistics
from datetime import UTC, datetime

from sqlalchemy import select

from nicheradar.config import Settings
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.database import database_engine

MINIMUM_SAMPLES = 5  # Same baseline_minimum already used for breakout classification.


def p90(samples: list[float]) -> float:
    return statistics.quantiles(samples, n=10, method="inclusive")[-1]


engine = database_engine(Settings())
with engine.connect() as connection:
    rows = (
        connection.execute(
            select(
                s.opportunities.c.format,
                s.analysis_runs.c.mode,
                s.evaluation_versions.c.explanation,
            )
            .select_from(s.evaluation_versions)
            .join(s.opportunities, s.opportunities.c.id == s.evaluation_versions.c.opportunity_id)
            .join(s.analysis_runs, s.analysis_runs.c.id == s.evaluation_versions.c.run_id)
        )
        .mappings()
        .all()
    )

samples: dict[str, dict[str, list[float]]] = {}
for row in rows:
    if row["mode"] == "synthetic":
        continue
    metrics = (row["explanation"] or {}).get("metrics") or {}
    demand = metrics.get("demand_by_age") or {}
    trend = metrics.get("trend_relative_change")
    bucket = samples.setdefault(row["format"], {"trend": []})
    for band, value in demand.items():
        if value is not None:
            bucket.setdefault(band, []).append(value)
    if trend is not None:
        bucket["trend"].append(abs(trend))

now = datetime.now(UTC).date().isoformat()
results = {}
for video_format, bucket in samples.items():
    demand_p90 = {
        band: p90(values)
        for band, values in bucket.items()
        if band != "trend" and len(values) >= MINIMUM_SAMPLES
    }
    trend_values = bucket["trend"]
    trend_p90 = p90(trend_values) if len(trend_values) >= MINIMUM_SAMPLES else None
    counts = {band: len(values) for band, values in bucket.items() if band != "trend"}
    if not demand_p90:
        results[video_format] = {
            "status": "insufficient_real_evidence",
            "sample_counts": counts,
            "trend_samples": len(trend_values),
        }
        continue
    excluded = {band: n for band, n in counts.items() if band not in demand_p90}
    results[video_format] = {
        "status": "candidate",
        "references": {
            "version": f"real-evidence-p90-{now}",
            "format": video_format,
            "source": (
                f"Percentil 90 (statistics.quantiles, n=10, inclusive) sobre evaluaciones "
                f"reales no sintéticas hasta {now}. Muestras por franja: {counts}. "
                f"Excluidas por <{MINIMUM_SAMPLES} muestras: {excluded or 'ninguna'}."
            ),
            "synthetic": False,
            "reviewed": False,
            "demand_p90_by_age": demand_p90,
            "trend_p90_abs_change": trend_p90,
        },
        "sample_counts": counts,
        "trend_samples": len(trend_values),
    }

print(json.dumps(results))
