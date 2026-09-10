from collections.abc import Mapping
from pathlib import Path
from unittest.mock import Mock, patch

import pydantic
import pytest
import requests

from dstack._internal.core.consts import DSTACK_SHIM_HTTP_PORT
from dstack._internal.core.errors import SSHError
from dstack._internal.server.schemas.runner import HealthcheckResponse
from dstack._internal.server.services.runner.client import (
    LocalAddress,
    PeerConnectionError,
    ShimResponseBodyError,
    ShimResponseError,
    ShimResponseStatusError,
)
from dstack._internal.server.services.runner.ssh import runner_ssh_tunnel
from dstack._internal.server.testing.common import get_job_provisioning_data

FORWARDED_PATHS = {DSTACK_SHIM_HTTP_PORT: Path("/tmp/shim.sock")}


def _shim_response(status_code: int, content: bytes) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response._content = content
    response.request = requests.Request(
        method="GET", url="http://localhost/api/tasks/id"
    ).prepare()
    return response


def _make_error(error_cls: type[ShimResponseError]) -> ShimResponseError:
    """Builds either leaf of the `ShimResponseError` family without going through a client."""
    if error_cls is ShimResponseStatusError:
        return ShimResponseStatusError(_shim_response(404, b"Task not found"))
    try:
        HealthcheckResponse.model_validate({})
    except pydantic.ValidationError as error:
        return ShimResponseBodyError(_shim_response(200, b"{}"), error)
    raise AssertionError("expected a validation error")


class BaseRunnerSSHTunnelTest:
    @pytest.fixture
    def conn(self):
        conn = Mock()
        conn.forwarded_paths.return_value = FORWARDED_PATHS
        return conn

    def call(self, func, dockerized: bool = False, jpd=None):
        decorated = runner_ssh_tunnel(func)
        if jpd is None:
            jpd = get_job_provisioning_data(dockerized=dockerized)
        return decorated(("private_key", None), jpd, None)

    def test_missing_connection_details_raise(self):
        jpd = get_job_provisioning_data().model_copy(update={"hostname": None})

        with pytest.raises(PeerConnectionError, match="hostname or SSH port is not known"):
            self.call(lambda addresses: "result", jpd=jpd)


class TestEphemeralConnection(BaseRunnerSSHTunnelTest):
    """`dockerized=False` takes the branch that opens a fresh connection per call."""

    @pytest.fixture(autouse=True)
    def instance_connection(self, conn):
        with patch(
            "dstack._internal.server.services.runner.ssh.InstanceConnection", return_value=conn
        ):
            yield conn

    def test_returns_result(self, conn):
        assert self.call(lambda addresses: "result") == "result"
        assert conn.close.call_count == 1

    def test_ssh_error_on_open_raises(self, conn):
        conn.open.side_effect = SSHError("no route")

        with pytest.raises(PeerConnectionError, match="failed to open an SSH connection") as exc:
            self.call(lambda addresses: "result")
        assert isinstance(exc.value.__cause__, SSHError)

    @pytest.mark.parametrize(
        "exc",
        [
            requests.ConnectionError("refused"),
            requests.ReadTimeout("too slow"),
            requests.exceptions.ChunkedEncodingError("truncated"),
        ],
    )
    def test_connection_errors_raise(self, conn, exc):
        def func(addresses: Mapping[int, LocalAddress]):
            raise exc

        with pytest.raises(PeerConnectionError, match="did not get through") as raised:
            self.call(func)
        assert raised.value.__cause__ is exc
        # the connection is still released
        assert conn.close.call_count == 1

    @pytest.mark.parametrize("error_cls", [ShimResponseStatusError, ShimResponseBodyError])
    def test_api_errors_propagate(self, conn, error_cls):
        def func(addresses: Mapping[int, LocalAddress]):
            raise _make_error(error_cls)

        with pytest.raises(ShimResponseError):
            self.call(func)
        # the connection is still released
        assert conn.close.call_count == 1


class TestPooledConnection(BaseRunnerSSHTunnelTest):
    """`dockerized=True` takes the branch that reuses pooled connections."""

    @pytest.fixture(autouse=True)
    def pool(self, conn):
        with patch(
            "dstack._internal.server.services.runner.ssh.instance_connection_pool"
        ) as pool_mock:
            pool_mock.get_or_open.return_value = conn
            yield pool_mock

    def test_returns_result(self, pool):
        assert self.call(lambda addresses: "result", dockerized=True) == "result"
        assert pool.drop.call_count == 0

    def test_connection_error_drops_and_retries_once(self, pool):
        error = requests.ConnectionError("refused")

        def func(addresses: Mapping[int, LocalAddress]):
            raise error

        with pytest.raises(PeerConnectionError, match="did not get through") as raised:
            self.call(func, dockerized=True)
        assert raised.value.__cause__ is error
        assert pool.get_or_open.call_count == 2
        assert pool.drop.call_count == 2

    def test_other_connection_errors_do_not_retry(self, pool):
        def func(addresses: Mapping[int, LocalAddress]):
            raise requests.ReadTimeout("too slow")

        with pytest.raises(PeerConnectionError, match="did not get through"):
            self.call(func, dockerized=True)
        assert pool.get_or_open.call_count == 1
        assert pool.drop.call_count == 0

    def test_unopenable_connection_raises(self, pool):
        pool.get_or_open.return_value = None

        with pytest.raises(PeerConnectionError, match="failed to open an SSH connection"):
            self.call(lambda addresses: "result", dockerized=True)

    @pytest.mark.parametrize("error_cls", [ShimResponseStatusError, ShimResponseBodyError])
    def test_api_errors_propagate(self, pool, error_cls):
        def func(addresses: Mapping[int, LocalAddress]):
            raise _make_error(error_cls)

        with pytest.raises(ShimResponseError):
            self.call(func, dockerized=True)
        assert pool.get_or_open.call_count == 1
        assert pool.drop.call_count == 0
