"""Re-validate and re-derive the stored evidence without calling the model (no cost).

Usage: rederive_evidence.py [--apply]     (default: dry run, nothing is written)
Each stored `model_evidence` goes through the current `raw_text` check (so a value the parser
used to misread is dropped) and `build_derived`, then the derived columns are rewritten. Idempotent.
"""

import json
import sys
from decimal import Decimal
from typing import Any

from sqlalchemy import Engine, select, update

from nicheradar.config import Settings
from nicheradar.market_intel.evidence.contracts import ModelEvidence
from nicheradar.market_intel.evidence.reconcile import drop_unverifiable_entries
from nicheradar.market_intel.evidence.summary import build_derived
from nicheradar.repositories.database import database_engine
from nicheradar.repositories.schema import listing_evidence as le
from nicheradar.repositories.schema import marketplace_listings as ml


def rederive(engine: Engine, *, apply: bool) -> dict[str, int]:
    counts = {"rows": 0, "changed": 0, "grade_changed": 0, "entries_dropped": 0, "invalid": 0}
    with engine.begin() as connection:
        rows = connection.execute(
            select(
                le.c.id,
                le.c.model_evidence,
                le.c.derived,
                le.c.extracted_at,
                le.c.evidence_grade,
                ml.c.income_monthly_usd,
            )
            .join(ml, ml.c.id == le.c.listing_id)
            .where(le.c.extraction_state == "complete", le.c.model_evidence.is_not(None))
        ).all()
        for row in rows:
            counts["rows"] += 1
            try:
                before = ModelEvidence.model_validate(row.model_evidence)
            except ValueError:
                counts["invalid"] += 1
                continue
            after = drop_unverifiable_entries(before)
            counts["entries_dropped"] += (len(before.earnings) + len(before.views)) - (
                len(after.earnings) + len(after.views)
            )
            derived: dict[str, Any] = build_derived(
                after,
                fx={},
                extracted_at=row.extracted_at,
                declared_income=row.income_monthly_usd,
            )
            if row.derived and "call" in row.derived:
                derived["call"] = row.derived["call"]
            if derived == row.derived and after == before:
                continue
            counts["changed"] += 1
            counts["grade_changed"] += derived["evidence_grade"] != row.evidence_grade
            if apply:
                connection.execute(
                    update(le)
                    .where(le.c.id == row.id)
                    .values(
                        model_evidence=after.model_dump(mode="json"),
                        derived=derived,
                        evidence_grade=derived["evidence_grade"],
                        income_level=derived["income_level"],
                        observed_monthly_income_usd=(
                            Decimal(derived["observed_monthly_income_usd"])
                            if derived["observed_monthly_income_usd"]
                            else None
                        ),
                        rpm_usd=Decimal(derived["rpm_usd"]) if derived["rpm_usd"] else None,
                        rpm_sample_eligible=bool(derived["rpm_sample_eligible"]),
                    )
                )
    return counts


def main() -> None:
    apply = "--apply" in sys.argv[1:]
    result = rederive(database_engine(Settings()), apply=apply)
    print(json.dumps({"applied": apply, **result}))


if __name__ == "__main__":
    main()
