from pathlib import Path

import pytest
from alembic.command import check, downgrade, upgrade
from alembic.config import Config
from alembic.util.exc import CommandError
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer


def test_sqlite_migrations(monkeypatch: pytest.MonkeyPatch):
    server_dir = Path(__file__).parent.joinpath("../../../dstack/_internal/server").resolve()
    monkeypatch.chdir(server_dir)

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.attributes["connection"] = create_engine("sqlite://").connect()
    # disable fileConfig() call in env.py as it breaks pytest.LogCaptureFixture
    alembic_cfg.attributes["configure_logging"] = False

    try:
        upgrade(alembic_cfg, "head")
        check(alembic_cfg)
        downgrade(alembic_cfg, "base")
    except CommandError as e:
        pytest.fail(str(e))


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_postgres_migrations(monkeypatch: pytest.MonkeyPatch):
    def f(connection, alembic_cfg):
        alembic_cfg.attributes["connection"] = connection
        # disable fileConfig() call in env.py as it breaks pytest.LogCaptureFixture
        alembic_cfg.attributes["configure_logging"] = False
        try:
            upgrade(alembic_cfg, "head")
            check(alembic_cfg)
            downgrade(alembic_cfg, "base")
        except CommandError as e:
            pytest.fail(str(e))

    server_dir = Path(__file__).parent.joinpath("../../../dstack/_internal/server").resolve()
    monkeypatch.chdir(server_dir)
    alembic_cfg = Config("alembic.ini")
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as postgres:
        db_url = postgres.get_connection_url()
        # This is needed to run offline(sync) migrations via async driver
        # https://alembic.sqlalchemy.org/en/latest/cookbook.html#programmatic-api-use-connection-sharing-with-asyncio
        engine = create_async_engine(db_url)
        async with engine.connect() as conn:
            await conn.run_sync(f, alembic_cfg)
