from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, Engine, create_engine

from nicheradar.config import Settings


def database_engine(settings: Settings) -> Engine:
    if settings.database_url is None:
        raise RuntimeError("NR_DATABASE_URL is not configured")
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_size=3,
        max_overflow=0,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"options": "-c timezone=UTC -c statement_timeout=15000"},
    )


@contextmanager
def transaction(engine: Engine) -> Iterator[Connection]:
    """Commit only on normal exit; all exceptions trigger PostgreSQL rollback."""
    with engine.begin() as connection:
        yield connection
