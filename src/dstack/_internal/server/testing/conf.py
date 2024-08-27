import pytest
import pytest_asyncio
from testcontainers.postgres import PostgresContainer

from dstack._internal.server.db import Database, override_db
from dstack._internal.server.models import BaseModel


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as postgres:
        yield postgres.get_connection_url()


@pytest_asyncio.fixture
async def test_db(request):
    db_type = getattr(request, "param", "sqlite")
    if db_type == "sqlite":
        db_url = "sqlite+aiosqlite://"
    elif db_type == "postgres":
        if not request.config.getoption("--runpostgres"):
            pytest.skip("Skipping Postgres tests as --runpostgres was not provided")
        db_url = request.getfixturevalue("postgres_container")
    else:
        raise ValueError(f"Unknown db_type {db_type}")
    db = Database(db_url)
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
