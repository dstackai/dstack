from collections.abc import Mapping
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from dstack._internal.core.consts import DSTACK_SHIM_HTTP_PORT
from dstack._internal.core.errors import SSHError
from dstack._internal.server.services.runner.client import LocalAddress, ShimHTTPError
from dstack._internal.server.services.runner.ssh import runner_ssh_tunnel
from dstack._internal.server.testing.common import get_job_provisioning_data

FORWARDED_PATHS = {DSTACK_SHIM_HTTP_PORT: Path("/tmp/shim.sock")}


class BaseRunnerSSHTunnelTest:
    @pytest.fixture
    def conn(self):
        conn = Mock()
        conn.forwarded_paths.return_value = FORWARDED_PATHS
        return conn

    def call(self, func, dockerized: bool = False):
        decorated = runner_ssh_tunnel(func)
        return decorated(
            ("private_key", None), get_job_provisioning_data(dockerized=dockerized), None
        )


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

    def test_ssh_error_on_open_returns_false(self, conn):
        conn.open.side_effect = SSHError("no route")

        assert self.call(lambda addresses: "result") is False

    @pytest.mark.parametrize(
        "exc",
        [
            requests.ConnectionError("refused"),
            requests.ReadTimeout("too slow"),
            requests.exceptions.ChunkedEncodingError("truncated"),
        ],
    )
    def test_connection_errors_return_false(self, conn, exc):
        def func(addresses: Mapping[int, LocalAddress]):
            raise exc

        assert self.call(func) is False
        assert conn.close.call_count == 1

    def test_api_errors_propagate(self, conn):
        def func(addresses: Mapping[int, LocalAddress]):
            try:
                raise requests.exceptions.HTTPError("404 Client Error: Not Found")
            except requests.exceptions.HTTPError as e:
                raise ShimHTTPError() from e

        with pytest.raises(ShimHTTPError):
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
        def func(addresses: Mapping[int, LocalAddress]):
            raise requests.ConnectionError("refused")

        assert self.call(func, dockerized=True) is False
        assert pool.get_or_open.call_count == 2
        assert pool.drop.call_count == 2

    def test_other_connection_errors_do_not_retry(self, pool):
        def func(addresses: Mapping[int, LocalAddress]):
            raise requests.ReadTimeout("too slow")

        assert self.call(func, dockerized=True) is False
        assert pool.get_or_open.call_count == 1
        assert pool.drop.call_count == 0

    def test_api_errors_propagate(self, pool):
        def func(addresses: Mapping[int, LocalAddress]):
            try:
                raise requests.exceptions.HTTPError("404 Client Error: Not Found")
            except requests.exceptions.HTTPError as e:
                raise ShimHTTPError() from e

        with pytest.raises(ShimHTTPError):
            self.call(func, dockerized=True)
        assert pool.get_or_open.call_count == 1
        assert pool.drop.call_count == 0
