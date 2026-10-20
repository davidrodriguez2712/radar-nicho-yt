# scripts/run_market_scrape_once.py
"""Manual, bounded pilot run of the market scraper.

Ignores the schedule pause (it is meant for the supervised pilot) but never the live gate:
NR_MARKET_INTEL_LIVE_ENABLED must be true in live mode. Prints a JSON summary, never secrets.
"""

import argparse
import json

from nicheradar.config import Settings
from nicheradar.market_intel.manual import run_once


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one bounded market scrape")
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--detail-cap", type=int, default=20)
    parser.add_argument("--classify-cap", type=int, default=10)
    parser.add_argument("--verify-cap", type=int, default=5)
    args = parser.parse_args()
    config = Settings().model_copy(
        update={
            "market_intel_max_pages": args.max_pages,
            "market_intel_detail_cap_per_run": args.detail_cap,
            "market_intel_classify_cap_per_run": args.classify_cap,
            "market_intel_verify_cap_per_run": args.verify_cap,
        }
    )
    print(json.dumps(run_once(config), default=str))


if __name__ == "__main__":
    main()
