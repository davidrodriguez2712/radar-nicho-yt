"""Read-only spend by provider/operation since a date (default 30 days); prints model names."""

import argparse
import json
from datetime import UTC, datetime, timedelta

from nicheradar.config import Settings
from nicheradar.repositories.database import database_engine
from nicheradar.subniche_discovery.report import spend_rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()
    config = Settings()
    engine = database_engine(config)
    since = datetime.now(UTC) - timedelta(days=args.days)
    with engine.connect() as connection:
        rows = spend_rows(connection, since)
    models = {
        "openai": config.llm_configuration.tariff.model if config.llm_configuration else None,
        "anthropic": config.anthropic_configuration.tariff.model
        if config.anthropic_configuration
        else None,
    }
    print(json.dumps({"since": since.isoformat(), "models": models, "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
