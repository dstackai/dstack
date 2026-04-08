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


# test_db is function-scoped since making it session-scoped did not bring much benefit.
@pytest_asyncio.fixture
async def test_db(request):
    db_type = getattr(request, "param", "sqlite")
    engine = None
    if db_type == "sqlite":
        db_url = "sqlite+aiosqlite://"
        # For SQLite, allow accessing the in-memory DB from multiple threads:
        # https://docs.sqlalchemy.org/en/13/dialects/sqlite.html#using-a-memory-database-in-multiple-threads
        engine = create_async_engine(
            db_url,
            echo=settings.SQL_ECHO_ENABLED,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    elif db_type == "postgres":
        if not request.config.getoption("--runpostgres"):
            pytest.skip("Skipping Postgres tests as --runpostgres was not provided")
        db_url = request.getfixturevalue("postgres_container")
    else:
        raise ValueError(f"Unknown db_type {db_type}")
    db = Database(db_url, engine=engine)
    override_db(db)
    if db_type == "sqlite":
        async with db.engine.begin() as conn:
            await conn.run_sync(BaseModel.metadata.create_all)
            # Relying on function-scoped engine for a clean DB
    else:
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
