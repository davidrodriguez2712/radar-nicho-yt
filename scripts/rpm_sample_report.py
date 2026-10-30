"""Read-only report: observed long-form RPM by niche, with the Shorts rule applied at read time.

Usage: rpm_sample_report.py [min_n]   (default 1: niches with at least `min_n` eligible listings)
Aggregates only; it prints no listing content and stores nothing.
"""

import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, text

from nicheradar.config import Settings
from nicheradar.market_intel.evidence.sample import (
    SampleContext,
    sample_decision,
    shorts_share_of_views,
)
from nicheradar.repositories.database import database_engine

CATALOG = Path(__file__).parent.parent / "src/nicheradar/data/youtube_niches_rpm_longform_2026.json"
QUERY = """
select e.derived, e.extracted_at,
  e.model_evidence -> 'monetization' ->> 'monetized_since' as monetized_since,
  (select niche_label from listing_classifications c where c.listing_id = l.id
     order by c.created_at desc limit 1) as niche,
  snap.recent_videos, snap.channel_created_at, snap.country
from listing_evidence e join marketplace_listings l on l.id = e.listing_id
left join lateral (
  select s.recent_videos, s.channel_created_at, s.country from listing_channel_snapshots s
  where s.listing_id = l.id and s.status = 'ok' order by s.fetched_at desc limit 1
) snap on true
where e.prompt_version like '%p7' and e.extraction_state = 'complete'
  and e.derived ->> 'rpm_sample_eligible' = 'true'
"""


def context_of(
    derived: dict[str, Any],
    extracted_at: datetime,
    monetized_since: str | None,
    videos: list[dict[str, Any]] | None,
    created_at: datetime | None,
    country: str | None,
) -> SampleContext:
    """The reference day is the capture's (extraction minus its age), not today's."""
    age = (derived.get("primary") or {}).get("capture_age_days")
    reference = (extracted_at - timedelta(days=int(age or 0))).date()
    return SampleContext(
        shorts_share=shorts_share_of_views(videos) if videos else None,
        channel_age_days=(reference - created_at.date()).days if created_at else None,
        country=country,
        monetized_days=(reference - date.fromisoformat(monetized_since)).days
        if monetized_since
        else None,
        tier1_share=derived.get("tier1_share"),
    )


def quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def build_report(engine: Engine, minimum: int = 1) -> list[str]:
    catalog = {
        item["niche_label"]: (item["rate_low"] + item["rate_high"]) / 2
        for item in json.loads(CATALOG.read_text())
    }
    reasons: Counter[str] = Counter()
    rpm_by_niche: dict[str, list[float]] = defaultdict(list)
    with engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        rows = list(connection.execute(text(QUERY)))
    for derived, extracted_at, since, niche, videos, created_at, country in rows:
        reason = sample_decision(
            derived, context_of(derived, extracted_at, since, videos, created_at, country)
        )
        reasons[reason] += 1
        if reason == "ok":
            rpm_by_niche[niche or "(sin clasificar)"].append(float(Decimal(derived["rpm_usd"])))
    lines = [f"elegibles segun la derivacion guardada: {len(rows)} {dict(reasons)}"]
    every = [v for values in rpm_by_niche.values() for v in values]
    if every:
        p10, p25, p50, p75, p90 = (quantile(every, q) for q in (0.1, 0.25, 0.5, 0.75, 0.9))
        lines.append(
            f"RPM de la muestra de formato largo: n={len(every)} p10={p10:.2f} p25={p25:.2f} "
            f"mediana={p50:.2f} p75={p75:.2f} p90={p90:.2f}"
        )
    lines.append("nicho | n | RPM mediano | p25-p75 | RPM catalogo (punto medio)")
    for niche, values in sorted(rpm_by_niche.items(), key=lambda item: -len(item[1])):
        if len(values) >= minimum:
            ref = catalog.get(niche)
            reference = f"{ref:.2f}" if ref is not None else "-"
            lines.append(
                f"{niche} | {len(values)} | {statistics.median(values):.2f} | "
                f"{quantile(values, 0.25):.2f}-{quantile(values, 0.75):.2f} | {reference}"
            )
    return lines


def main() -> None:
    minimum = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    print("\n".join(build_report(database_engine(Settings()), minimum)))


if __name__ == "__main__":
    main()
