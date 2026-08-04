from collections.abc import Generator
from functools import cache
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
from dstack._internal.utils import ssh as ssh_utils


def _warm_up_route_schemas() -> None:
    """
    Build every route's pydantic schemas once, at import time.

    FastAPI builds a route's dependant lazily, on the first request that matches it. Several tests
    make that first request inside `@freeze_time`, where `datetime.datetime` is freezegun's
    `FakeDatetime`. pydantic v2 matches `datetime` by exact type and rejects the subclass, so a
    route with an `Optional[datetime]` query parameter (`after`, `before`) fails to build with
    `PydanticSchemaGenerationError` — and because `FakeDatetime` mimics `datetime`'s repr, the
    error names `datetime.datetime` and reads like a production bug.

    Doing this eagerly, before any test freezes the clock, keeps the schemas built from the real
    types. Nothing in production freezes time, so this is a test-environment fix only.
    """
    # FastAPI 0.141 defers this to `_IncludedRouter.effective_candidates()`, reached from
    # `matches()` on the first request. Duck-typed rather than importing the private class.
    pending = list(app.routes)
    while pending:
        route = pending.pop()
        build = getattr(route, "effective_candidates", None)
        if callable(build):
            pending.extend(build())


_warm_up_route_schemas()


@pytest.fixture(scope="session", autouse=True)
def cache_parsed_ssh_keys():
    """
    Parses each SSH key once per session instead of once per call.

    Parsing an RSA key costs ~190ms because paramiko validates it, and fleet spec
    validation parses the same handful of test keys over and over.
    """
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(ssh_utils, "pkey_from_str", cache(ssh_utils.pkey_from_str))
        yield


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
    image_config = ImageConfig.model_validate(
        {"User": None, "Entrypoint": None, "Cmd": ["/bin/bash"]}
    )
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
