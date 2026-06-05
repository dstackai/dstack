from contextlib import asynccontextmanager, contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dstack._internal.server.services.runs.router_worker_sync import (
    _get_connection_mode_from_workers,
    _get_grpc_worker_payload,
    _get_runtime_type_from_workers,
    _get_worker_payload,
    _grpc_server_info_to_worker_payload,
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


class TestGrpcServerInfoToWorkerPayload:
    def test_vllm_prefill(self):
        response = MagicMock(kv_role="kv_producer", kv_connector="NixlConnector")
        payload = _grpc_server_info_to_worker_payload("grpc://10.0.0.1:50051", "vllm", response)
        assert payload["worker_type"] == "prefill"
        assert payload["runtime_type"] == "vllm"
        assert payload["kv_role"] == "kv_producer"

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
            payload = _grpc_server_info_to_worker_payload(
                "grpc://10.0.0.1:8000", "sglang", response
            )
        assert payload == {
            "url": "grpc://10.0.0.1:8000",
            "worker_type": "prefill",
            "connection_mode": "grpc",
            "runtime_type": "sglang",
            "bootstrap_port": 8998,
        }


@contextmanager
def _fake_vllm_grpc_proto(*, server_info: MagicMock):
    stub = MagicMock()
    stub.GetServerInfo = AsyncMock(return_value=server_info)
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
def _fake_sglang_grpc_proto(*, server_info: MagicMock):
    stub = MagicMock()
    stub.GetServerInfo = AsyncMock(return_value=server_info)
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


@pytest.mark.asyncio
async def test_get_grpc_worker_payload_ready():
    job = MagicMock()
    channel = MagicMock()

    @asynccontextmanager
    async def _fake_grpc_client(_job):
        yield channel

    server_info = MagicMock(kv_role="kv_producer", kv_connector="NixlConnector")

    with (
        _fake_vllm_grpc_proto(server_info=server_info),
        patch(
            "dstack._internal.server.services.runs.router_worker_sync.get_service_replica_grpc_client",
            _fake_grpc_client,
        ),
    ):
        result = await _get_grpc_worker_payload(
            job,
            worker_url="grpc://10.0.0.1:50051",
            runtime_type="vllm",
        )

    assert result["status"] == "ready"
    assert result["payload"] == {
        "url": "grpc://10.0.0.1:50051",
        "worker_type": "prefill",
        "connection_mode": "grpc",
        "runtime_type": "vllm",
        "kv_connector": "NixlConnector",
        "kv_role": "kv_producer",
    }


@pytest.mark.asyncio
async def test_get_grpc_worker_payload_not_ready_on_error():
    job = MagicMock()

    @asynccontextmanager
    async def _failing_client(_job):
        raise OSError("ssh failed")
        yield  # pragma: no cover

    with patch(
        "dstack._internal.server.services.runs.router_worker_sync.get_service_replica_grpc_client",
        _failing_client,
    ):
        result = await _get_grpc_worker_payload(job, worker_url="grpc://10.0.0.1:50051")

    assert result == {"status": "not_ready", "payload": None}


@pytest.mark.asyncio
async def test_get_grpc_worker_payload_sglang_bootstrap():
    job = MagicMock()
    channel = MagicMock()
    sglang_server_info = MagicMock(server_args=MagicMock())

    @asynccontextmanager
    async def _fake_grpc_client(_job):
        yield channel

    with (
        _fake_sglang_grpc_proto(server_info=sglang_server_info),
        patch(
            "dstack._internal.server.services.runs.router_worker_sync.MessageToDict",
            return_value={
                "disaggregation_mode": "prefill",
                "disaggregation_bootstrap_port": 8998,
            },
        ),
        patch(
            "dstack._internal.server.services.runs.router_worker_sync"
            ".get_service_replica_grpc_client",
            _fake_grpc_client,
        ),
    ):
        result = await _get_grpc_worker_payload(job, worker_url="grpc://10.0.0.1:8000")

    assert result["status"] == "ready"
    assert result["payload"] == {
        "url": "grpc://10.0.0.1:8000",
        "worker_type": "prefill",
        "connection_mode": "grpc",
        "runtime_type": "sglang",
        "bootstrap_port": 8998,
    }


@pytest.mark.asyncio
async def test_get_worker_payload_grpc_preference_skips_http():
    job = MagicMock()
    grpc_not_ready = {"status": "not_ready", "payload": None}

    with (
        patch(
            "dstack._internal.server.services.runs.router_worker_sync._get_grpc_worker_payload",
            new_callable=AsyncMock,
            return_value=grpc_not_ready,
        ) as grpc_mock,
        patch(
            "dstack._internal.server.services.runs.router_worker_sync._get_http_worker_payload",
            new_callable=AsyncMock,
        ) as http_mock,
    ):
        result = await _get_worker_payload(
            job,
            http_worker_url="http://10.0.0.1:8000",
            grpc_worker_url="grpc://10.0.0.1:8000",
            connection_mode="grpc",
        )

    assert result == grpc_not_ready
    grpc_mock.assert_awaited_once()
    http_mock.assert_not_awaited()
