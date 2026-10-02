"""Postgres tests use an explicitly isolated database, never the application DB."""

import os
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, inspect
from sqlalchemy.engine import URL, make_url


@pytest.fixture(scope="session")
def postgres_engine() -> Iterator[Engine]:
    binaries = os.environ.get("NR_TEST_POSTGRES_BIN")
    test_url = os.environ.get("NR_TEST_DATABASE_URL")
    with tempfile.TemporaryDirectory(
        prefix="nrpg-",
        dir="/private/tmp" if os.name == "posix" and Path("/private/tmp").is_dir() else None,
    ) as temporary:
        directory = Path(temporary)
        process_started = False
        if binaries:
            binary_dir = Path(binaries)
            subprocess.run(
                [
                    str(binary_dir / "initdb"),
                    "-D",
                    str(directory / "data"),
                    "-U",
                    "nicheradar_test",
                    "--auth-local=trust",
                    "--auth-host=reject",
                    "--encoding=UTF8",
                    "--no-locale",
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    str(binary_dir / "pg_ctl"),
                    "-D",
                    str(directory / "data"),
                    "-l",
                    str(directory / "postgres.log"),
                    "-o",
                    f"-k {directory} -h '' -p 55439 -c max_connections=20",
                    "-w",
                    "start",
                ],
                check=True,
                capture_output=True,
            )
            process_started = True
            url = URL.create(
                "postgresql+psycopg",
                username="nicheradar_test",
                database="postgres",
                query={"host": str(directory), "port": "55439"},
            )
        elif test_url:
            url = make_url(test_url)
            if url.host not in {"127.0.0.1", "localhost"} or not (url.database or "").startswith(
                "nicheradar_test"
            ):
                pytest.fail("NR_TEST_DATABASE_URL must point to a local nicheradar_test* database")
        else:
            pytest.skip("Set NR_TEST_POSTGRES_BIN or an isolated NR_TEST_DATABASE_URL")
        engine = create_engine(
            url,
            hide_parameters=True,
            connect_args={"options": "-c timezone=UTC -c statement_timeout=5000"},
        )
        try:
            with engine.begin() as conn:
                if inspect(conn).get_table_names():
                    pytest.fail("Refusing to migrate a nonempty test database")
                config = Config("alembic.ini")
                config.attributes["connection"] = conn
                command.upgrade(config, "head")
            yield engine
        finally:
            engine.dispose()
            if process_started:
                subprocess.run(
                    [
                        str(Path(binaries or "") / "pg_ctl"),
                        "-D",
                        str(directory / "data"),
                        "-m",
                        "fast",
                        "-w",
                        "stop",
                    ],
                    check=True,
                    capture_output=True,
                )


@pytest.fixture
def db(postgres_engine: Engine) -> Iterator[Connection]:
    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()


@pytest.fixture
def isolated_engine(postgres_engine: Engine) -> Iterator[Engine]:
    schema_name = "nrtest_" + uuid4().hex
    with postgres_engine.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema_name}"')
    engine = create_engine(
        postgres_engine.url,
        hide_parameters=True,
        connect_args={
            "options": f"-c search_path={schema_name} -c timezone=UTC -c statement_timeout=5000"
        },
    )
    try:
        with engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        with postgres_engine.begin() as connection:
            # Only the unique schema created above; never an application/default schema.
            connection.exec_driver_sql(f'DROP SCHEMA "{schema_name}" CASCADE')
