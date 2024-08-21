from pathlib import Path

import pytest
import pytest_asyncio

from dstack._internal.server.db import Database, override_db
from dstack._internal.server.models import BaseModel
from dstack._internal.server.services import encryption as encryption  # import for side-effect
from dstack._internal.server.services import logs as logs_services

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


@pytest.fixture
def test_log_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> logs_services.FileLogStorage:
    root = tmp_path / "test_logs"
    root.mkdir()
    storage = logs_services.FileLogStorage(root)
    monkeypatch.setattr(logs_services, "_default_log_storage", storage)
    return storage
