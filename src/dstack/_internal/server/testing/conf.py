import pytest
import pytest_asyncio
from sqlalchemy import StaticPool
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from dstack._internal.server import settings
from dstack._internal.server.db import Database, override_db
from dstack._internal.server.models import BaseModel

# Remember initialized URLs to create metadata once per session.
_initialized_postgres_db_urls = set()


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as postgres:
        yield postgres.get_connection_url()


SQLITE_URL = "sqlite+aiosqlite://"


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


@pytest_asyncio.fixture
async def test_db(request, sqlite_db):
    db_type = getattr(request, "param", "sqlite")
    if db_type == "sqlite":
        override_db(sqlite_db)
        await _delete_all_rows(sqlite_db)
        yield sqlite_db
        return
    if db_type != "postgres":
        raise ValueError(f"Unknown db_type {db_type}")
    if not request.config.getoption("--runpostgres"):
        pytest.skip("Skipping Postgres tests as --runpostgres was not provided")
    db_url = request.getfixturevalue("postgres_container")
    db = Database(db_url)
    override_db(db)
    if db_url not in _initialized_postgres_db_urls:
        async with db.engine.begin() as conn:
            await conn.run_sync(BaseModel.metadata.create_all)
        _initialized_postgres_db_urls.add(db_url)
    await _truncate_postgres_db(db)
    yield db
    await db.engine.dispose()


@pytest_asyncio.fixture
async def session(test_db):
    db = test_db
    async with db.get_session() as session:
        yield session


async def _delete_all_rows(db: Database):
    async with db.engine.begin() as conn:
        for table in reversed(BaseModel.metadata.sorted_tables):
            await conn.exec_driver_sql(f'DELETE FROM "{table.name}"')


async def _truncate_postgres_db(db: Database):
    preparer = db.engine.sync_engine.dialect.identifier_preparer
    table_names = ", ".join(
        preparer.format_table(table) for table in BaseModel.metadata.sorted_tables
    )
    if not table_names:
        return
    truncate_statement = f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"
    async with db.engine.begin() as conn:
        await conn.exec_driver_sql(truncate_statement)
