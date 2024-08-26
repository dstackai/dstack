import os
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from dstack._internal.server.db import Database, override_db
from dstack._internal.server.main import app
from dstack._internal.server.models import BaseModel
from dstack._internal.server.services import encryption as encryption  # import for side-effect
from dstack._internal.server.services import logs as logs_services


def get_database_url(db_type: str) -> str:
    if db_type == "sqlite":
        return "sqlite+aiosqlite://"
    if db_type == "postgres":
        db_url = os.getenv("DSTACK_DATABASE_TEST_URL")
        if db_url is None:
            raise ValueError("DSTACK_DATABASE_TEST_URL not set")
        return db_url
    raise ValueError(f"Unknown db_type {db_type}")


@pytest_asyncio.fixture
async def test_db(request):
    db_type = getattr(request, "param", "sqlite")
    db_url = get_database_url(db_type)
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


@pytest.fixture
def client(event_loop):
    return httpx.AsyncClient(app=app, base_url="http://test")


@pytest.fixture
def test_log_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> logs_services.FileLogStorage:
    root = tmp_path / "test_logs"
    root.mkdir()
    storage = logs_services.FileLogStorage(root)
    monkeypatch.setattr(logs_services, "_default_log_storage", storage)
    return storage
