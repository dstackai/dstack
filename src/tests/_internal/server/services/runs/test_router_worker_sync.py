import json
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import httpx
import pytest
from httpx import AsyncClient

from dstack._internal.core.errors import SSHError
from dstack._internal.server.services.runs import router_worker_sync
from dstack._internal.server.services.runs.router_worker_sync import (
    _get_connection_mode_from_workers,
    _get_router_workers,
    _get_runtime_type_from_workers,
    _get_worker,
    _grpc_server_info_to_worker,
    _probe_grpc_worker,
    _probe_http_worker,
)


class TestGetConnectionModeFromWorkers:
    def test_grpc(self):
        current = [{"connection_mode": "grpc"}]
        assert _get_connection_mode_from_workers(current) == "grpc"

    def test_http(self):
        current = [{"connection_mode": "http"}]
        assert _get_connection_mode_from_workers(current) == "http"

    def test_mixed(self):
        current = [{"connection_mode": "grpc"}, {"connection_mode": "http"}]
        assert _get_connection_mode_from_workers(current) is None


class TestRuntimeTypeFromRouterWorkers:
    def test_vllm_grpc_workers(self):
        current = [{"connection_mode": "grpc", "runtime_type": "vllm"}]
        assert _get_runtime_type_from_workers(current) == "vllm"

    def test_sglang_grpc_workers(self):
        current = [{"connection_mode": "grpc", "runtime_type": "sglang"}]
        assert _get_runtime_type_from_workers(current) == "sglang"

    def test_ignores_http_workers(self):
        current = [{"connection_mode": "http", "runtime_type": "sglang"}]
        assert _get_runtime_type_from_workers(current) is None

    def test_mixed_runtimes(self):
        current = [
            {"connection_mode": "grpc", "runtime_type": "vllm"},
            {"connection_mode": "grpc", "runtime_type": "sglang"},
        ]
        assert _get_runtime_type_from_workers(current) is None


class TestGrpcServerInfoToWorker:
    def test_vllm_prefill(self):
        response = MagicMock(kv_role="kv_producer", kv_connector="NixlConnector")
        worker = _grpc_server_info_to_worker("grpc://10.0.0.1:50051", "vllm", response)
        assert worker["worker_type"] == "prefill"
        assert worker.get("runtime_type") == "vllm"
        assert worker.get("kv_role") == "kv_producer"

    def test_sglang_prefill(self):
        server_args = MagicMock()
        response = MagicMock(server_args=server_args)
        with patch(
            "dstack._internal.server.services.runs.router_worker_sync.MessageToDict",
            return_value={
                "disaggregation_mode": "prefill",
                "disaggregation_bootstrap_port": 8998,
            },
        ):
            worker = _grpc_server_info_to_worker("grpc://10.0.0.1:8000", "sglang", response)
        assert worker == {
            "url": "grpc://10.0.0.1:8000",
            "worker_type": "prefill",
            "connection_mode": "grpc",
            "runtime_type": "sglang",
            "bootstrap_port": 8998,
        }


def _router_client(handler) -> AsyncClient:
    return AsyncClient(transport=httpx.MockTransport(handler))


def _json_response(status_code: int, payload) -> httpx.Response:
    return httpx.Response(status_code, content=json.dumps(payload).encode())


@pytest.mark.asyncio
class TestGetRouterWorkers:
    """
    `[]` must mean "the router really has no workers", so every response that does not carry a
    usable worker list has to come back as `None`. Otherwise the caller reconciles against a
    fabricated empty list and re-adds every worker, see
    https://github.com/dstackai/dstack/issues/4300.
    """

    async def test_returns_workers(self):
        payload = {"workers": [{"id": "1", "url": "http://10.0.0.1:8000"}]}
        async with _router_client(lambda _: _json_response(200, payload)) as client:
            assert await _get_router_workers(client) == payload["workers"]

    async def test_returns_empty_list_when_router_has_no_workers(self):
        async with _router_client(lambda _: _json_response(200, {"workers": []})) as client:
            assert await _get_router_workers(client) == []

    async def test_returns_none_on_unexpected_status(self):
        async with _router_client(lambda _: _json_response(500, {"workers": []})) as client:
            assert await _get_router_workers(client) is None

    async def test_returns_none_on_unparsable_body(self):
        async with _router_client(lambda _: httpx.Response(200, content=b"not json")) as client:
            assert await _get_router_workers(client) is None

    async def test_returns_none_when_body_is_not_an_object(self):
        async with _router_client(lambda _: _json_response(200, ["a"])) as client:
            assert await _get_router_workers(client) is None

    async def test_returns_none_when_workers_key_is_missing(self):
        async with _router_client(lambda _: _json_response(200, {})) as client:
            assert await _get_router_workers(client) is None

    async def test_returns_none_when_workers_is_not_an_array(self):
        async with _router_client(lambda _: _json_response(200, {"workers": "oops"})) as client:
            assert await _get_router_workers(client) is None

    async def test_returns_none_on_request_error(self, caplog: pytest.LogCaptureFixture):
        def handler(_):
            # What an SSH tunnel to a port nobody listens on yet produces.
            raise httpx.ReadError("")

        caplog.set_level(level=logging.DEBUG, logger=router_worker_sync.__name__)
        async with _router_client(handler) as client:
            assert await _get_router_workers(client) is None
        # A router that has not bound its port yet is expected, not an error.
        assert "Router /workers not ready yet" in caplog.text
        assert not [r for r in caplog.records if r.levelno > logging.DEBUG]


@pytest.mark.asyncio
class TestProbeHttpWorker:
    """
    The probe talks to the replica over the tunnel, but the `url` it reports is the address the
    router dials. It must stay byte-identical to what the router echoes back in `/workers`,
    otherwise `_update_workers_in_router_replica` re-registers every worker on each sync.
    """

    async def test_regular_worker(self):
        async with _router_client(lambda _: _json_response(200, {"status": "ready"})) as client:
            assert await _probe_http_worker(client, address="10.0.0.1:8000") == {
                "url": "http://10.0.0.1:8000",
                "worker_type": "regular",
                "connection_mode": "http",
                "runtime_type": "sglang",
            }

    async def test_prefill_worker(self):
        payload = {
            "status": "ready",
            "disaggregation_mode": "prefill",
            "disaggregation_bootstrap_port": 8998,
        }
        async with _router_client(lambda _: _json_response(200, payload)) as client:
            assert await _probe_http_worker(client, address="10.0.0.1:8000") == {
                "url": "http://10.0.0.1:8000",
                "worker_type": "prefill",
                "connection_mode": "http",
                "runtime_type": "sglang",
                "bootstrap_port": 8998,
            }

    async def test_decode_worker(self):
        payload = {"status": "ready", "disaggregation_mode": "decode"}
        async with _router_client(lambda _: _json_response(200, payload)) as client:
            worker = await _probe_http_worker(client, address="10.0.0.1:8000")
        assert worker is not None
        assert worker["worker_type"] == "decode"

    async def test_returns_none_when_not_ready(self):
        payload = {"status": "starting"}
        async with _router_client(lambda _: _json_response(200, payload)) as client:
            assert await _probe_http_worker(client, address="10.0.0.1:8000") is None

    async def test_returns_none_on_request_error(self, caplog: pytest.LogCaptureFixture):
        def handler(_):
            # A gRPC-only worker, or one that has not bound its port yet.
            raise httpx.ReadError("")

        caplog.set_level(level=logging.DEBUG, logger=router_worker_sync.__name__)
        async with _router_client(handler) as client:
            assert await _probe_http_worker(client, address="10.0.0.1:8000") is None
        # Repeats every sync until the worker is up, so it must not be logged as an error,
        # see https://github.com/dstackai/dstack/issues/4300.
        assert "Could not fetch server_info for worker http://10.0.0.1:8000" in caplog.text
        assert not [r for r in caplog.records if r.levelno > logging.DEBUG]


@contextmanager
def _fake_vllm_grpc_proto(*, server_info=None, error: Optional[Exception] = None):
    stub = MagicMock()
    stub.GetServerInfo = AsyncMock(return_value=server_info, side_effect=error)
    pb2 = MagicMock(GetServerInfoRequest=MagicMock(return_value="req"))
    pb2_grpc = MagicMock(VllmEngineStub=MagicMock(return_value=stub))
    with (
        patch(
            "dstack._internal.server.services.runs.router_worker_sync.vllm_engine_pb2",
            pb2,
        ),
        patch(
            "dstack._internal.server.services.runs.router_worker_sync.vllm_engine_pb2_grpc",
            pb2_grpc,
        ),
    ):
        yield


@contextmanager
def _fake_sglang_grpc_proto(*, server_info=None, error: Optional[Exception] = None):
    stub = MagicMock()
    stub.GetServerInfo = AsyncMock(return_value=server_info, side_effect=error)
    pb2 = MagicMock(GetServerInfoRequest=MagicMock(return_value="req"))
    pb2_grpc = MagicMock(SglangSchedulerStub=MagicMock(return_value=stub))
    with (
        patch(
            "dstack._internal.server.services.runs.router_worker_sync.sglang_scheduler_pb2",
            pb2,
        ),
        patch(
            "dstack._internal.server.services.runs.router_worker_sync.sglang_scheduler_pb2_grpc",
            pb2_grpc,
        ),
    ):
        yield


def _rpc_error(code: grpc.StatusCode) -> grpc.aio.AioRpcError:
    return grpc.aio.AioRpcError(code, grpc.aio.Metadata(), grpc.aio.Metadata(), details=code.name)


@pytest.mark.asyncio
class TestProbeGrpcWorker:
    async def test_known_runtime_type(self):
        server_info = MagicMock(kv_role="kv_producer", kv_connector="NixlConnector")
        with _fake_vllm_grpc_proto(server_info=server_info):
            worker = await _probe_grpc_worker(
                MagicMock(), address="10.0.0.1:50051", runtime_type="vllm"
            )
        assert worker == {
            "url": "grpc://10.0.0.1:50051",
            "worker_type": "prefill",
            "connection_mode": "grpc",
            "runtime_type": "vllm",
            "kv_connector": "NixlConnector",
            "kv_role": "kv_producer",
        }

    async def test_bootstrap_tries_sglang_first(self):
        with (
            _fake_sglang_grpc_proto(server_info=MagicMock(server_args=MagicMock())),
            patch(
                "dstack._internal.server.services.runs.router_worker_sync.MessageToDict",
                return_value={
                    "disaggregation_mode": "prefill",
                    "disaggregation_bootstrap_port": 8998,
                },
            ),
        ):
            worker = await _probe_grpc_worker(MagicMock(), address="10.0.0.1:8000")
        assert worker == {
            "url": "grpc://10.0.0.1:8000",
            "worker_type": "prefill",
            "connection_mode": "grpc",
            "runtime_type": "sglang",
            "bootstrap_port": 8998,
        }

    async def test_bootstrap_falls_back_to_vllm(self):
        # A vLLM worker does not implement the SGLang scheduler service.
        with (
            _fake_sglang_grpc_proto(error=_rpc_error(grpc.StatusCode.UNIMPLEMENTED)),
            _fake_vllm_grpc_proto(
                server_info=MagicMock(kv_role="kv_consumer", kv_connector="NixlConnector")
            ),
        ):
            worker = await _probe_grpc_worker(MagicMock(), address="10.0.0.1:8000")
        assert worker is not None
        assert worker["runtime_type"] == "vllm"
        assert worker["worker_type"] == "decode"

    @pytest.mark.parametrize(
        "code",
        [
            # No listener yet, or an SSH tunnel to a dead remote port, or an HTTP-only worker.
            grpc.StatusCode.UNAVAILABLE,
            grpc.StatusCode.DEADLINE_EXCEEDED,
            grpc.StatusCode.UNIMPLEMENTED,
        ],
    )
    async def test_returns_none_on_expected_error(self, code: grpc.StatusCode):
        with _fake_vllm_grpc_proto(error=_rpc_error(code)):
            worker = await _probe_grpc_worker(
                MagicMock(), address="10.0.0.1:8000", runtime_type="vllm"
            )
        assert worker is None

    async def test_reraises_unexpected_error(self):
        error = _rpc_error(grpc.StatusCode.PERMISSION_DENIED)
        with _fake_vllm_grpc_proto(error=error), pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await _probe_grpc_worker(MagicMock(), address="10.0.0.1:8000", runtime_type="vllm")
        assert exc_info.value is error

    async def test_returns_none_when_no_runtime_type_matches(self):
        with (
            _fake_sglang_grpc_proto(error=_rpc_error(grpc.StatusCode.UNAVAILABLE)),
            _fake_vllm_grpc_proto(error=_rpc_error(grpc.StatusCode.UNAVAILABLE)),
        ):
            worker = await _probe_grpc_worker(MagicMock(), address="10.0.0.1:8000")
        assert worker is None


_HTTP_WORKER = {
    "url": "http://10.0.0.1:8000",
    "worker_type": "regular",
    "connection_mode": "http",
    "runtime_type": "sglang",
}
_GRPC_WORKER = {
    "url": "grpc://10.0.0.1:8000",
    "worker_type": "prefill",
    "connection_mode": "grpc",
    "runtime_type": "vllm",
}


def _async_cm(enter_value=None, enter_error: Optional[Exception] = None) -> AsyncMock:
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=enter_value, side_effect=enter_error)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


@contextmanager
def _fake_replica_transports(
    *,
    uds_path: Path = Path("/tmp/replica.sock"),
    tunnel_error: Optional[Exception] = None,
    http_worker=None,
    grpc_worker=None,
):
    """Patch the tunnel and both probes, leaving `_get_worker`'s own logic intact."""
    mocks = MagicMock()
    with (
        patch(
            "dstack._internal.server.services.runs.router_worker_sync.get_service_replica_tunnel",
            return_value=_async_cm(uds_path, tunnel_error),
        ) as mocks.tunnel,
        patch(
            "dstack._internal.server.services.runs.router_worker_sync"
            ".get_service_replica_http_client_over_uds",
            return_value=_async_cm(MagicMock()),
        ) as mocks.http_client,
        patch(
            "dstack._internal.server.services.runs.router_worker_sync"
            ".get_service_replica_grpc_channel_over_uds",
            return_value=_async_cm(MagicMock()),
        ) as mocks.grpc_channel,
        patch(
            "dstack._internal.server.services.runs.router_worker_sync._probe_http_worker",
            new_callable=AsyncMock,
            return_value=http_worker,
        ) as mocks.http_probe,
        patch(
            "dstack._internal.server.services.runs.router_worker_sync._probe_grpc_worker",
            new_callable=AsyncMock,
            return_value=grpc_worker,
        ) as mocks.grpc_probe,
    ):
        yield mocks


@pytest.mark.asyncio
class TestGetWorker:
    async def test_connection_mode_grpc_skips_http(self):
        with _fake_replica_transports(grpc_worker=_GRPC_WORKER) as mocks:
            worker = await _get_worker(
                MagicMock(),
                address="10.0.0.1:8000",
                connection_mode="grpc",
            )
        assert worker == _GRPC_WORKER
        mocks.grpc_probe.assert_awaited_once()
        mocks.http_probe.assert_not_awaited()

    async def test_connection_mode_http_skips_grpc(self):
        with _fake_replica_transports(http_worker=_HTTP_WORKER) as mocks:
            worker = await _get_worker(
                MagicMock(),
                address="10.0.0.1:8000",
                connection_mode="http",
            )
        assert worker == _HTTP_WORKER
        mocks.http_probe.assert_awaited_once()
        mocks.grpc_probe.assert_not_awaited()

    async def test_bootstrap_probes_http_first(self):
        # An HTTP worker must not pay for two gRPC `GetServerInfo` timeouts first.
        with _fake_replica_transports(http_worker=_HTTP_WORKER, grpc_worker=_GRPC_WORKER) as mocks:
            worker = await _get_worker(
                MagicMock(),
                address="10.0.0.1:8000",
            )
        assert worker == _HTTP_WORKER
        mocks.http_probe.assert_awaited_once()
        mocks.grpc_probe.assert_not_awaited()

    async def test_bootstrap_falls_back_to_grpc_over_one_tunnel(self):
        job = MagicMock()
        uds_path = Path("/tmp/replica.sock")
        with _fake_replica_transports(uds_path=uds_path, grpc_worker=_GRPC_WORKER) as mocks:
            worker = await _get_worker(
                job,
                address="10.0.0.1:8000",
            )
        assert worker == _GRPC_WORKER
        mocks.tunnel.assert_called_once_with(job)
        mocks.http_client.assert_called_once_with(uds_path)
        mocks.grpc_channel.assert_called_once_with(uds_path)
        mocks.http_probe.assert_awaited_once()
        mocks.grpc_probe.assert_awaited_once()

    async def test_returns_none_when_no_mode_reports_ready(self):
        with _fake_replica_transports() as mocks:
            worker = await _get_worker(
                MagicMock(),
                address="10.0.0.1:8000",
            )
        assert worker is None
        mocks.http_probe.assert_awaited_once()
        mocks.grpc_probe.assert_awaited_once()

    async def test_unreachable_worker_is_skipped_not_raised(
        self, caplog: pytest.LogCaptureFixture
    ):
        # One dead replica must not abort the sync for the healthy ones.
        caplog.set_level(level=logging.WARNING, logger=router_worker_sync.__name__)
        ssh_error = SSHError("connection refused")
        with _fake_replica_transports(tunnel_error=ssh_error) as mocks:
            worker = await _get_worker(
                MagicMock(),
                address="10.0.0.1:8000",
            )
        assert worker is None
        mocks.http_probe.assert_not_awaited()
        mocks.grpc_probe.assert_not_awaited()
        assert f"failed to connect to worker replica: {ssh_error!r}" in caplog.text

    async def test_unexpected_tunnel_error_propagates(self):
        # Only `SSHError` means "unreachable"; anything else is a bug and must not be swallowed.
        with _fake_replica_transports(tunnel_error=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                await _get_worker(
                    MagicMock(),
                    address="10.0.0.1:8000",
                )
