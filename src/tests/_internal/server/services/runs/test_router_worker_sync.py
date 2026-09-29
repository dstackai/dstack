import json
import logging
import uuid
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import SSHError
from dstack._internal.core.models.configurations import parse_run_configuration
from dstack._internal.core.models.runs import JobStatus, RunStatus
from dstack._internal.server.models import JobModel, RunModel
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.runs import router_worker_sync
from dstack._internal.server.services.runs.router_worker_sync import (
    _add_worker_to_router,
    _get_connection_mode_from_workers,
    _get_router_workers,
    _get_runtime_type_from_workers,
    _get_worker,
    _get_workers_diff,
    _grpc_server_info_to_worker,
    _probe_grpc_worker,
    _probe_http_worker,
    _TargetWorker,
    sync_router_workers_for_run_model,
)
from dstack._internal.server.testing.common import (
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_run_spec,
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
class TestAddWorkerToRouter:
    """
    `_TargetWorker` is sent as the `POST /workers` body as is. `TypedDict` does not reject extra
    keys at runtime, and the router silently ignores unknown ones, so this test is what catches a
    field that should not go over the wire.
    """

    @pytest.mark.parametrize(
        "worker",
        [
            pytest.param(
                {
                    "url": "http://10.0.0.1:8000",
                    "worker_type": "regular",
                    "connection_mode": "http",
                    "runtime_type": "sglang",
                },
                id="http-regular",
            ),
            pytest.param(
                {
                    "url": "grpc://10.0.0.1:8000",
                    "worker_type": "prefill",
                    "connection_mode": "grpc",
                    "runtime_type": "vllm",
                    "bootstrap_port": 8998,
                    "kv_connector": "NixlConnector",
                    "kv_role": "kv_producer",
                },
                id="grpc-prefill",
            ),
        ],
    )
    async def test_posts_worker_as_is(self, worker: _TargetWorker):
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return _json_response(202, {"status": "accepted"})

        async with _router_client(handler) as client:
            assert await _add_worker_to_router(client, worker) is True
        assert len(requests) == 1
        assert requests[0].method == "POST"
        assert requests[0].url.path == "/workers"
        assert json.loads(requests[0].content) == worker

    async def test_returns_false_when_not_accepted(self, caplog: pytest.LogCaptureFixture):
        worker: _TargetWorker = {
            "url": "http://10.0.0.1:8000",
            "worker_type": "regular",
            "connection_mode": "http",
            "runtime_type": "sglang",
        }
        async with _router_client(lambda _: _json_response(202, {"status": "rejected"})) as client:
            assert await _add_worker_to_router(client, worker) is False
        assert "Unexpected add-worker response for http://10.0.0.1:8000" in caplog.text


@pytest.mark.asyncio
class TestProbeHttpWorker:
    """
    The probe talks to the replica over the tunnel, but the `url` it reports is the address the
    router dials. It must stay byte-identical to what the router echoes back in `/workers`,
    otherwise `_get_workers_diff` re-registers every worker on each sync.
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


class TestGetWorkersDiff:
    def test_adds_missing_and_removes_extra_workers(self):
        kept: _TargetWorker = {
            "url": "http://10.0.0.1:8000",
            "worker_type": "regular",
            "connection_mode": "http",
            "runtime_type": "sglang",
        }
        added: _TargetWorker = {**kept, "url": "http://10.0.0.2:8000"}
        current = [
            # The router may echo the URL back with a trailing slash
            {"id": "1", "url": "http://10.0.0.1:8000/"},
            {"id": "2", "url": "http://10.0.0.3:8000"},
        ]
        diff = _get_workers_diff([kept, added], current)
        assert diff.to_add == [added]
        assert diff.to_remove == {"http://10.0.0.3:8000": "2"}
        assert not diff.is_empty()

    def test_is_empty_when_router_is_in_sync(self):
        worker: _TargetWorker = {
            "url": "http://10.0.0.1:8000",
            "worker_type": "regular",
            "connection_mode": "http",
            "runtime_type": "sglang",
        }
        diff = _get_workers_diff([worker], [{"id": "1", "url": "http://10.0.0.1:8000"}])
        assert diff.is_empty()

    def test_removed_worker_without_id(self):
        diff = _get_workers_diff([], [{"url": "http://10.0.0.1:8000"}])
        assert diff.to_remove == {"http://10.0.0.1:8000": None}


class _FakeRouter:
    """An in-memory router `/workers` API that counts the connections made to it."""

    def __init__(self, workers: Optional[list[dict]] = None, *, unreachable: bool = False):
        self.workers = list(workers or [])
        self.unreachable = unreachable
        self.connections = 0
        self.added: list[dict] = []
        self.removed_ids: list[str] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/workers":
            return _json_response(200, {"workers": self.workers})
        if request.method == "POST" and request.url.path == "/workers":
            worker = json.loads(request.content)
            self.added.append(worker)
            self.workers.append({"id": f"id-{len(self.added)}", **worker})
            return _json_response(202, {"status": "accepted"})
        if request.method == "DELETE" and request.url.path.startswith("/workers/"):
            worker_id = request.url.path.removeprefix("/workers/")
            self.removed_ids.append(worker_id)
            self.workers = [w for w in self.workers if w["id"] != worker_id]
            return _json_response(202, {"status": "accepted"})
        return httpx.Response(404)


@contextmanager
def _fake_router_replicas(routers: dict[uuid.UUID, _FakeRouter]):
    """Route each router job's client to its fake router, keyed by the job id."""

    @asynccontextmanager
    async def get_service_replica_client(job: JobModel):
        router = routers[job.id]
        router.connections += 1
        if router.unreachable:
            raise SSHError("connection refused")
        async with AsyncClient(transport=httpx.MockTransport(router.handle)) as client:
            yield client

    with patch(
        "dstack._internal.server.services.runs.router_worker_sync.get_service_replica_client",
        get_service_replica_client,
    ):
        yield


async def _create_router_service_run(session: AsyncSession, router_count: int) -> RunModel:
    project = await create_project(session=session)
    user = await create_user(session=session)
    repo = await create_repo(session=session, project_id=project.id)
    conf = parse_run_configuration(
        {
            "type": "service",
            "port": 8000,
            "gateway": False,
            "groups": [
                {
                    "name": "router",
                    "replicas": 1,
                    "commands": ["smg launch"],
                    "router": {"type": "sglang"},
                },
                {"name": "worker", "replicas": 1, "commands": ["worker"]},
            ],
        }
    )
    run = await create_run(
        session=session,
        project=project,
        repo=repo,
        user=user,
        status=RunStatus.RUNNING,
        run_spec=get_run_spec(repo_id=repo.name, run_name="test-run", configuration=conf),
    )
    # More than one running router means a rolling deployment is replacing the router
    for replica_num in range(router_count):
        await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            replica_num=replica_num,
            replica_group_name="router",
        )
    await session.refresh(run, attribute_names=["jobs"])
    return run


_VLLM_WORKER: _TargetWorker = {
    "url": "grpc://10.0.0.1:8000",
    "worker_type": "regular",
    "connection_mode": "grpc",
    "runtime_type": "vllm",
}


def _patch_build_target_workers(**kwargs):
    return patch(
        "dstack._internal.server.services.runs.router_worker_sync._build_target_workers",
        new_callable=AsyncMock,
        **kwargs,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestSyncRouterWorkersForRunModel:
    async def test_syncs_replacement_router_without_touching_up_to_date_one(
        self, test_db, session: AsyncSession
    ):
        run = await _create_router_service_run(session, router_count=2)
        old_router = _FakeRouter([{"id": "1", **_VLLM_WORKER}])
        new_router = _FakeRouter()
        routers = {run.jobs[0].id: old_router, run.jobs[1].id: new_router}

        with (
            _fake_router_replicas(routers),
            _patch_build_target_workers(return_value=[_VLLM_WORKER]) as build_mock,
        ):
            await sync_router_workers_for_run_model(run)

        assert new_router.added == [_VLLM_WORKER]
        assert old_router.added == []
        assert old_router.removed_ids == []
        # Read once; reconnected only for the router that needed an update
        assert old_router.connections == 1
        assert new_router.connections == 2
        # Workers are probed once for all routers, with hints taken from all of them: the
        # replacement router's empty list alone would mean "probe everything"
        build_mock.assert_awaited_once()
        assert build_mock.await_args is not None
        assert build_mock.await_args.kwargs["connection_mode"] == "grpc"
        assert build_mock.await_args.kwargs["runtime_type"] == "vllm"

    async def test_unreachable_router_does_not_block_others(
        self, test_db, session: AsyncSession, caplog: pytest.LogCaptureFixture
    ):
        caplog.set_level(level=logging.WARNING, logger=router_worker_sync.__name__)
        run = await _create_router_service_run(session, router_count=2)
        unreachable_router = _FakeRouter(unreachable=True)
        reachable_router = _FakeRouter()
        routers = {run.jobs[0].id: unreachable_router, run.jobs[1].id: reachable_router}

        with (
            _fake_router_replicas(routers),
            _patch_build_target_workers(return_value=[_VLLM_WORKER]),
        ):
            await sync_router_workers_for_run_model(run)

        assert reachable_router.added == [_VLLM_WORKER]
        assert unreachable_router.connections == 1
        assert f"{fmt(run.jobs[0])}: failed to sync workers with router" in caplog.text

    async def test_skips_probing_workers_when_no_router_is_reachable(
        self, test_db, session: AsyncSession
    ):
        run = await _create_router_service_run(session, router_count=1)
        routers = {run.jobs[0].id: _FakeRouter(unreachable=True)}

        with _fake_router_replicas(routers), _patch_build_target_workers() as build_mock:
            await sync_router_workers_for_run_model(run)

        build_mock.assert_not_awaited()

    async def test_rereads_router_workers_before_updating(self, test_db, session: AsyncSession):
        run = await _create_router_service_run(session, router_count=1)
        router = _FakeRouter([{"id": "1", **_VLLM_WORKER}])
        routers = {run.jobs[0].id: router}

        def reregister_worker(*args, **kwargs):
            # Worker ids are assigned by the router. Here, the worker got a new one while the
            # workers were being probed, so the id read before probing is stale.
            router.workers = [{"id": "2", **_VLLM_WORKER}]
            return []

        with (
            _fake_router_replicas(routers),
            _patch_build_target_workers(side_effect=reregister_worker),
        ):
            await sync_router_workers_for_run_model(run)

        assert router.removed_ids == ["2"]
        assert router.workers == []
