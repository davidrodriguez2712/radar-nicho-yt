"""Read-only ranking of measured sub-niche hypotheses (JSON)."""

import json

from nicheradar.config import Settings
from nicheradar.repositories.database import database_engine
from nicheradar.subniche_discovery.report import ranking


def main() -> None:
    engine = database_engine(Settings())
    with engine.connect() as connection:
        print(json.dumps({"ranking": ranking(connection)}, default=str, indent=2))


if __name__ == "__main__":
    main()
