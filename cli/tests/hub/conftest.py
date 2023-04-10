import pytest_asyncio

from dstack.hub.db import Database, override_db
from dstack.hub.db.models import Base

db = Database("sqlite+aiosqlite://")
override_db(db)


@pytest_asyncio.fixture
async def test_db():
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        yield conn
        await conn.run_sync(Base.metadata.drop_all)
