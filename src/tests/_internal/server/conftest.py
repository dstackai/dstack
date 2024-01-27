import pytest_asyncio

from dstack._internal.server.db import Database, override_db
from dstack._internal.server.models import BaseModel

db = Database("sqlite+aiosqlite://")
override_db(db)


@pytest_asyncio.fixture
async def test_db():
    async with db.engine.begin() as conn:
        await conn.run_sync(BaseModel.metadata.create_all)
        yield conn
        await conn.run_sync(BaseModel.metadata.drop_all)


@pytest_asyncio.fixture
async def session():
    async with db.get_session() as session:
        yield session
        await session.commit()
