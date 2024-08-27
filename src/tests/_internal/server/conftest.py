from pathlib import Path

import httpx
import pytest

from dstack._internal.server.main import app
from dstack._internal.server.services import encryption as encryption  # import for side-effect
from dstack._internal.server.services import logs as logs_services
from dstack._internal.server.testing.conf import postgres_container, session, test_db  # noqa: F401


@pytest.fixture
def client(event_loop):
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def test_log_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> logs_services.FileLogStorage:
    root = tmp_path / "test_logs"
    root.mkdir()
    storage = logs_services.FileLogStorage(root)
    monkeypatch.setattr(logs_services, "_default_log_storage", storage)
    return storage
