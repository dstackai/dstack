from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

from dstack._internal.server.main import app
from dstack._internal.server.services import encryption as encryption  # import for side-effect
from dstack._internal.server.services import logs as logs_services
from dstack._internal.server.services.docker import ImageConfig, ImageConfigObject
from dstack._internal.server.services.logs.filelog import FileLogStorage
from dstack._internal.server.testing.conf import postgres_container, session, test_db  # noqa: F401


@pytest.fixture
def client(event_loop):
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
