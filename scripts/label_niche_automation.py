# scripts/label_niche_automation.py
"""One-time labelling of automation priors for the 218 niches. Live only; spends LLM budget.

Run in small batches (--limit) and re-run until the output reports pending == 0.
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime

from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.market_intel.priors import close_analysis_run, label_niche_priors
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.repositories.database import database_engine


def main() -> None:
    parser = argparse.ArgumentParser(description="Label niche automation priors")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()
    config = Settings()
    if config.mode != "live" or not config.llm_enabled:
        raise SystemExit(
            "requires NR_MODE=live and the LLM enabled (see docs/market-intel-pilot.md)"
        )
    engine = database_engine(config)
    now = datetime.now(UTC)
    with engine.begin() as connection:
        profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
        run_id = insert_record(
            connection,
            "analysis_runs",
            {
                "profile_id": profile_id,
                "mode": "live",
                "trigger": "market_scrape",
                "status": "running",
                "configuration": {"purpose": "niche_automation_priors"},
            },
        )
    run = {"id": run_id, "profile_id": profile_id, "mode": "live"}
    try:
        result = asyncio.run(label_niche_priors(engine, run, config, now, limit=args.limit))
    except BaseException:
        close_analysis_run(engine, run_id, "failed", datetime.now(UTC))
        raise
    close_analysis_run(engine, run_id, "succeeded", datetime.now(UTC))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
