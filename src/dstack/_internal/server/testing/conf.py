import pytest
import pytest_asyncio
from sqlalchemy import StaticPool
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.community.postgres import PostgresContainer

from dstack._internal.server import settings
from dstack._internal.server.db import Database, override_db
from dstack._internal.server.models import BaseModel

SQLITE_URL = "sqlite+aiosqlite://"


@pytest.fixture(scope="session", autouse=True)
def server_dir(tmp_path_factory: pytest.TempPathFactory):
    """
    Points the server dir at a tmp dir private to this pytest process.

    The real `~/.dstack/server` is shared by every process on the machine, including a
    developer's running server and, under `pytest -n auto`, the other workers. Sharing it
    makes unrelated tests race over the same connection dirs and SSH control sockets.

    Everything the server derives from `SERVER_DIR_PATH` is resolved on access, so patching
    it here redirects all of it. `DSTACK_SERVER_DIR` is set too, for subprocesses.
    """
    path = tmp_path_factory.mktemp("server-dir")
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(settings, "SERVER_DIR_PATH", path)
        monkeypatch.setenv("DSTACK_SERVER_DIR", str(path))
        yield path


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer(
        "postgres:16-alpine",
        driver="asyncpg",
        # A test database never has to survive a crash, and fsync dominates commit cost.
        command="postgres -c fsync=off -c synchronous_commit=off -c full_page_writes=off",
    ) as postgres:
        yield postgres.get_connection_url()


@pytest_asyncio.fixture(scope="session")
async def sqlite_db():
    """
    A SQLite database with the schema created once for the whole session.

    Creating the schema costs ~20ms, so `test_db` clears the rows between tests
    instead of rebuilding the database per test.
    """
    engine = create_async_engine(
        SQLITE_URL,
        echo=settings.SQL_ECHO_ENABLED,
        # For SQLite, allow accessing the in-memory DB from multiple threads:
        # https://docs.sqlalchemy.org/en/13/dialects/sqlite.html#using-a-memory-database-in-multiple-threads
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db = Database(SQLITE_URL, engine=engine)
    async with engine.begin() as conn:
        await conn.run_sync(BaseModel.metadata.create_all)
    yield db
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def postgres_db(request):
    """
    A Postgres database with the schema created once for the whole session.

    Yields `None` without `--runpostgres` so that the container only starts when
    Postgres tests actually run.
    """
    if not request.config.getoption("--runpostgres"):
        yield None
        return
    db = Database(request.getfixturevalue("postgres_container"))
    async with db.engine.begin() as conn:
        await conn.run_sync(BaseModel.metadata.create_all)
    yield db
    await db.engine.dispose()


@pytest_asyncio.fixture
async def test_db(request, sqlite_db, postgres_db):
    db_type = getattr(request, "param", "sqlite")
    if db_type == "sqlite":
        db = sqlite_db
    elif db_type == "postgres":
        if postgres_db is None:
            pytest.skip("Skipping Postgres tests as --runpostgres was not provided")
        db = postgres_db
    else:
        raise ValueError(f"Unknown db_type {db_type}")
    override_db(db)
    await _clear_tables(db)
    yield db


@pytest_asyncio.fixture
async def session(test_db):
    db = test_db
    async with db.get_session() as session:
        yield session


async def _clear_tables(db: Database):
    """
    Removes every row, leaving the schema in place.

    Deletes in reverse dependency order so foreign keys stay satisfied. `DELETE` rather
    than `TRUNCATE` because Postgres takes an exclusive lock and rewrites files per
    `TRUNCATE`, which costs ~90ms for these tables against ~2ms to delete the rows.
    """
    preparer = db.engine.sync_engine.dialect.identifier_preparer
    names = [preparer.format_table(table) for table in reversed(BaseModel.metadata.sorted_tables)]
    statements = "".join(f"DELETE FROM {name};" for name in names)
    if db.dialect_name == "postgresql":
        async with db.engine.begin() as conn:
            await conn.exec_driver_sql(f"DO $$ BEGIN {statements} END $$;")
        return
    async with db.engine.connect() as conn:
        # SQLite has no multi-statement execute, and `executescript` commits on its own.
        aiosqlite_connection = (await conn.get_raw_connection()).driver_connection
        assert aiosqlite_connection is not None
        await aiosqlite_connection.executescript(statements)
