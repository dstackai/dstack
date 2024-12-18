import pytest
import pytest_asyncio
from sqlalchemy import StaticPool
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from dstack._internal.server import settings
from dstack._internal.server.db import Database, override_db
from dstack._internal.server.models import BaseModel


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as postgres:
        yield postgres.get_connection_url()


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
    async with db.engine.begin() as conn:
        await conn.run_sync(BaseModel.metadata.drop_all)
        await conn.run_sync(BaseModel.metadata.create_all)
    yield db
    async with db.engine.begin() as conn:
        await conn.run_sync(BaseModel.metadata.drop_all)
    await db.engine.dispose()


@pytest_asyncio.fixture
async def session(test_db):
    db = test_db
    async with db.get_session() as session:
        yield session
