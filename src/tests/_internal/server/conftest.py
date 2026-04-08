from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from dstack._internal.server.main import app
from dstack._internal.server.services import encryption as encryption  # import for side-effect
from dstack._internal.server.services import logs as logs_services
from dstack._internal.server.services.docker import ImageConfig, ImageConfigObject
from dstack._internal.server.services.logs.filelog import FileLogStorage
from dstack._internal.server.testing.conf import (  # noqa: F401
    postgres_container,
    session,
    test_db,
)


@pytest.fixture
def client():
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def test_log_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FileLogStorage:
    root = tmp_path / "test_logs"
    root.mkdir()
    storage = FileLogStorage(root)
    monkeypatch.setattr(logs_services, "_log_storage", storage)
    return storage


@pytest.fixture
def image_config_mock(monkeypatch: pytest.MonkeyPatch) -> ImageConfig:
    image_config = ImageConfig.parse_obj({"User": None, "Entrypoint": None, "Cmd": ["/bin/bash"]})
    monkeypatch.setattr(
        "dstack._internal.server.services.jobs.configurators.base._get_image_config",
        Mock(return_value=image_config),
    )
    monkeypatch.setattr(
        "dstack._internal.server.services.docker.get_image_config",
        Mock(return_value=ImageConfigObject(config=image_config)),
    )
    return image_config


@pytest.fixture()
def mock_gateway_connection() -> Generator[AsyncMock, None, None]:
    with patch(
        "dstack._internal.server.services.gateways.gateway_connections_pool.get_or_add"
    ) as get_conn_mock:
        get_conn_mock.return_value.client = Mock()
        get_conn_mock.return_value.client.return_value = AsyncMock()
        yield get_conn_mock
