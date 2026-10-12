import asyncio
import copy
import json
import logging
import uuid
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Optional, Union
from unittest.mock import AsyncMock, patch

import grpc
import httpx
import pytest
from google.protobuf.message import Message
from httpx import AsyncClient
from smg_grpc_proto import sglang_scheduler_pb2, vllm_engine_pb2
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import SSHError
from dstack._internal.core.models.configurations import (
    ServiceConfiguration,
    parse_run_configuration,
)
from dstack._internal.core.models.runs import JobStatus, RunStatus
from dstack._internal.server.models import JobModel, RunModel
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.runs import router_worker_sync
from dstack._internal.server.services.runs.router_worker_sync import (
    _add_worker_to_router,
    _get_current_worker_job_id,
    _get_router_workers,
    _get_worker_jobs_with_addresses,
    _probe_http_worker,
    _probe_sglang_grpc_worker,
    _probe_vllm_grpc_worker,
    _probe_worker_replica,
    _remove_worker_from_router,
    _TargetWorker,
    sync_router_workers_for_run_model,
)
from dstack._internal.server.testing.common import (
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_job_provisioning_data,
    get_run_spec,
)

# Hardcoded rather than imported: routers keep the label of every worker registered so far,
# so changing the key would break matching workers to jobs.
_JOB_ID_LABEL = "dstack.ai/job-id"

# Hardcoded rather than taken from the stubs: these are the services the workers serve.
_SGLANG_GET_SERVER_INFO = "/sglang.grpc.scheduler.SglangScheduler/GetServerInfo"
_VLLM_GET_SERVER_INFO = "/vllm.grpc.engine.VllmEngine/GetServerInfo"


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestSyncRouterWorkersForRunModel:
    async def test_registers_ready_workers_labeled_with_job_id(
        self, test_db, session: AsyncSession
    ):
        run, [router_job], worker_jobs = await _create_router_service_run(session, worker_count=3)
        router = _FakeRouter()
        # The second worker is not ready yet
        probe_results = {_worker_address(0): _http_worker(0), _worker_address(2): _http_worker(2)}

        with (
            _fake_router_replicas({router_job.id: router}),
            _fake_worker_probes(probe_results) as probe_mock,
        ):
            await sync_router_workers_for_run_model(run)

        assert [call.kwargs["address"] for call in probe_mock.await_args_list] == [
            _worker_address(0),
            _worker_address(1),
            _worker_address(2),
        ]
        assert router.added == [
            {**_http_worker(0), "labels": _job_id_label(worker_jobs[0])},
            {**_http_worker(2), "labels": _job_id_label(worker_jobs[2])},
        ]
        assert router.removed_ids == []

    async def test_does_not_probe_registered_workers(self, test_db, session: AsyncSession):
        # A registered worker is left to the router's own health checks
        run, [router_job], [worker_job] = await _create_router_service_run(session, worker_count=1)
        router = _FakeRouter(
            [_router_entry("w0", f"http://{_worker_address(0)}", _job_id_label(worker_job))]
        )

        with (
            _fake_router_replicas({router_job.id: router}),
            _fake_worker_probes({}) as probe_mock,
        ):
            await sync_router_workers_for_run_model(run)

        probe_mock.assert_not_awaited()
        assert router.added == []
        assert router.removed_ids == []
        # Read once, not connected to again, as there is nothing to update
        assert router.connections == 1

    async def test_removes_workers_of_jobs_no_longer_running(self, test_db, session: AsyncSession):
        run, [router_job], [running_job] = await _create_router_service_run(
            session, worker_count=1
        )
        stopped_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            replica_num=2,
            replica_group_name="worker",
            job_provisioning_data=get_job_provisioning_data(internal_ip="10.0.0.2"),
        )
        await session.refresh(run, attribute_names=["jobs"])
        router = _FakeRouter(
            [
                _router_entry(
                    "running", f"http://{_worker_address(0)}", _job_id_label(running_job)
                ),
                _router_entry(
                    "stopped", f"http://{_worker_address(1)}", _job_id_label(stopped_job)
                ),
            ]
        )

        with _fake_router_replicas({router_job.id: router}), _fake_worker_probes({}):
            await sync_router_workers_for_run_model(run)

        assert router.removed_ids == ["stopped"]
        assert router.added == []

    async def test_keeps_workers_registered_by_others(self, test_db, session: AsyncSession):
        run, [router_job], [worker_job] = await _create_router_service_run(session, worker_count=1)
        router = _FakeRouter(
            [
                _router_entry("dstack", f"http://{_worker_address(0)}", _job_id_label(worker_job)),
                _router_entry("unlabeled", "http://10.0.9.1:8000"),
                _router_entry("labeled", "http://10.0.9.2:8000", {"team": "ml"}),
            ]
        )

        with _fake_router_replicas({router_job.id: router}), _fake_worker_probes({}):
            await sync_router_workers_for_run_model(run)

        assert router.removed_ids == []
        assert router.connections == 1

    @pytest.mark.parametrize("scheme", ["http", "grpc"])
    async def test_matches_unlabeled_worker_by_address(
        self, test_db, session: AsyncSession, scheme: str
    ):
        # Workers registered before the job id label was introduced have no labels
        run, [router_job], _ = await _create_router_service_run(session, worker_count=1)
        router = _FakeRouter([_router_entry("legacy", f"{scheme}://{_worker_address(0)}")])

        with (
            _fake_router_replicas({router_job.id: router}),
            _fake_worker_probes({}) as probe_mock,
        ):
            await sync_router_workers_for_run_model(run)

        probe_mock.assert_not_awaited()
        assert router.added == []
        assert router.removed_ids == []

    async def test_registers_workers_in_replacement_router_only(
        self, test_db, session: AsyncSession
    ):
        # A rolling deployment runs the replacement router alongside the old one
        run, [old_router_job, new_router_job], [worker_job] = await _create_router_service_run(
            session, router_count=2, worker_count=1
        )
        old_router = _FakeRouter(
            [_router_entry("w0", f"http://{_worker_address(0)}", _job_id_label(worker_job))]
        )
        new_router = _FakeRouter()
        routers = {old_router_job.id: old_router, new_router_job.id: new_router}

        with (
            _fake_router_replicas(routers),
            _fake_worker_probes({_worker_address(0): _http_worker(0)}) as probe_mock,
        ):
            await sync_router_workers_for_run_model(run)

        # Probed anew rather than copied from the old router, see the comment in the code
        probe_mock.assert_awaited_once()
        assert new_router.added == [{**_http_worker(0), "labels": _job_id_label(worker_job)}]
        assert old_router.added == []
        # Read once, connected to again only if it needs updating
        assert old_router.connections == 1
        assert new_router.connections == 2

    @pytest.mark.parametrize(
        ["error", "message"],
        [
            pytest.param(
                SSHError("connection refused"),
                "failed to connect: SSHError('connection refused')",
                id="unreachable",
            ),
            pytest.param(
                RuntimeError("boom"), "unexpected error when getting workers", id="unexpected"
            ),
        ],
    )
    async def test_failing_router_does_not_block_others(
        self,
        test_db,
        session: AsyncSession,
        caplog: pytest.LogCaptureFixture,
        error: Exception,
        message: str,
    ):
        caplog.set_level(level=logging.WARNING, logger=router_worker_sync.__name__)
        run, [failing_router_job, router_job], [worker_job] = await _create_router_service_run(
            session, router_count=2, worker_count=1
        )
        failing_router = _FakeRouter(connect_error=error)
        router = _FakeRouter()
        routers = {failing_router_job.id: failing_router, router_job.id: router}

        with (
            _fake_router_replicas(routers),
            _fake_worker_probes({_worker_address(0): _http_worker(0)}),
        ):
            await sync_router_workers_for_run_model(run)

        assert router.added == [{**_http_worker(0), "labels": _job_id_label(worker_job)}]
        assert failing_router.connections == 1
        assert f"Router {fmt(failing_router_job)}: {message}" in caplog.text

    async def test_failing_router_update_does_not_block_others(
        self, test_db, session: AsyncSession, caplog: pytest.LogCaptureFixture
    ):
        caplog.set_level(level=logging.WARNING, logger=router_worker_sync.__name__)
        run, [failing_router_job, router_job], [worker_job] = await _create_router_service_run(
            session, router_count=2, worker_count=1
        )
        failing_router = _FakeRouter(update_error=RuntimeError("boom"))
        router = _FakeRouter()
        routers = {failing_router_job.id: failing_router, router_job.id: router}

        with (
            _fake_router_replicas(routers),
            _fake_worker_probes({_worker_address(0): _http_worker(0)}),
        ):
            await sync_router_workers_for_run_model(run)

        assert router.added == [{**_http_worker(0), "labels": _job_id_label(worker_job)}]
        assert (
            f"Router {fmt(failing_router_job)}: unexpected error when syncing workers"
            in caplog.text
        )

    async def test_skips_probing_when_no_router_returns_workers(
        self, test_db, session: AsyncSession
    ):
        run, [router_job], _ = await _create_router_service_run(session, worker_count=1)
        router = _FakeRouter(connect_error=SSHError("connection refused"))

        with (
            _fake_router_replicas({router_job.id: router}),
            _fake_worker_probes({_worker_address(0): _http_worker(0)}) as probe_mock,
        ):
            await sync_router_workers_for_run_model(run)

        probe_mock.assert_not_awaited()


@pytest.mark.asyncio
class TestProbeWorkerReplica:
    async def test_detects_http_sglang_worker(self):
        with _fake_replica_transports(
            http_handler=lambda _: httpx.Response(200, json={"status": "ready"}),
            # The HTTP/1.1 server answers the HTTP/2 preface with an error
            grpc_channel=_FakeGrpcChannel(unknown_method_code=grpc.StatusCode.UNAVAILABLE),
        ):
            worker = await _probe_worker_replica(_job(), address="10.0.0.1:8000")

        assert worker == {
            "url": "http://10.0.0.1:8000",
            "worker_type": "regular",
            "connection_mode": "http",
            "runtime_type": "sglang",
        }

    async def test_detects_sglang_grpc_worker(self):
        with _fake_replica_transports(
            http_handler=_grpc_server_http_handler,
            grpc_channel=_FakeGrpcChannel(
                {_SGLANG_GET_SERVER_INFO: sglang_scheduler_pb2.GetServerInfoResponse()}
            ),
        ):
            worker = await _probe_worker_replica(_job(), address="10.0.0.1:8000")

        assert worker == {
            "url": "grpc://10.0.0.1:8000",
            "worker_type": "regular",
            "connection_mode": "grpc",
            "runtime_type": "sglang",
        }

    async def test_detects_vllm_grpc_worker(self):
        with _fake_replica_transports(
            http_handler=_grpc_server_http_handler,
            grpc_channel=_FakeGrpcChannel(
                {_VLLM_GET_SERVER_INFO: vllm_engine_pb2.GetServerInfoResponse()}
            ),
        ):
            worker = await _probe_worker_replica(_job(), address="10.0.0.1:8000")

        assert worker == {
            "url": "grpc://10.0.0.1:8000",
            "worker_type": "regular",
            "connection_mode": "grpc",
            "runtime_type": "vllm",
        }

    async def test_returns_none_when_no_probe_succeeds(self):
        with _fake_replica_transports(
            http_handler=lambda _: httpx.Response(200, json={"status": "starting"}),
            grpc_channel=_FakeGrpcChannel(unknown_method_code=grpc.StatusCode.UNAVAILABLE),
        ):
            assert await _probe_worker_replica(_job(), address="10.0.0.1:8000") is None

    async def test_cancels_pending_probes_after_success(self):
        grpc_channel = _FakeGrpcChannel(hang=True)
        with _fake_replica_transports(
            http_handler=lambda _: httpx.Response(200, json={"status": "ready"}),
            grpc_channel=grpc_channel,
        ):
            worker = await _probe_worker_replica(_job(), address="10.0.0.1:8000")

        assert worker is not None
        assert worker["connection_mode"] == "http"
        assert sorted(grpc_channel.cancelled) == [_SGLANG_GET_SERVER_INFO, _VLLM_GET_SERVER_INFO]

    async def test_failing_probe_does_not_hide_successful_one(
        self, caplog: pytest.LogCaptureFixture
    ):
        def http_handler(request: httpx.Request) -> httpx.Response:
            raise RuntimeError("boom")

        job = _job()
        with _fake_replica_transports(
            http_handler=http_handler,
            grpc_channel=_FakeGrpcChannel(
                {_VLLM_GET_SERVER_INFO: vllm_engine_pb2.GetServerInfoResponse()}
            ),
        ):
            worker = await _probe_worker_replica(job, address="10.0.0.1:8000")

        assert worker is not None
        assert worker["runtime_type"] == "vllm"
        assert f"Worker {fmt(job)}: probe failed unexpectedly" in caplog.text

    @pytest.mark.parametrize(
        ["error", "message"],
        [
            pytest.param(
                SSHError("connection refused"),
                "failed to connect: SSHError('connection refused')",
                id="unreachable",
            ),
            pytest.param(RuntimeError("boom"), "unexpected error when probing", id="unexpected"),
        ],
    )
    async def test_returns_none_on_tunnel_error(
        self, caplog: pytest.LogCaptureFixture, error: Exception, message: str
    ):
        caplog.set_level(level=logging.WARNING, logger=router_worker_sync.__name__)
        job = _job()
        with _fake_replica_transports(tunnel_error=error):
            assert await _probe_worker_replica(job, address="10.0.0.1:8000") is None
        assert f"Worker {fmt(job)}: {message}" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestGetWorkerJobsWithAddresses:
    async def test_returns_running_worker_jobs_with_addresses(
        self, test_db, session: AsyncSession
    ):
        run, _, _ = await _create_router_service_run(session)
        with_internal_ip = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            replica_num=1,
            replica_group_name="worker",
            job_provisioning_data=get_job_provisioning_data(
                internal_ip="10.0.0.1", hostname="203.0.113.1"
            ),
        )
        without_internal_ip = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            replica_num=2,
            replica_group_name="worker",
            job_provisioning_data=get_job_provisioning_data(
                internal_ip=None, hostname="worker.example"
            ),
        )
        # Skipped: not provisioned
        await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            replica_num=3,
            replica_group_name="worker",
        )
        # Skipped: not running
        await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            replica_num=4,
            replica_group_name="worker",
            job_provisioning_data=get_job_provisioning_data(internal_ip="10.0.0.4"),
        )
        await session.refresh(run, attribute_names=["jobs"])

        result = _get_worker_jobs_with_addresses(
            run.jobs, configuration=_service_configuration(), router_group_name="router"
        )

        assert [(job.id, address) for job, address in result] == [
            (with_internal_ip.id, "10.0.0.1:8000"),
            (without_internal_ip.id, "worker.example:8000"),
        ]


class TestGetCurrentWorkerJobId:
    def test_returns_job_id_from_label(self):
        job_id = uuid.uuid4()
        worker = {"id": "1", "url": "http://10.0.0.1:8000", "labels": {_JOB_ID_LABEL: str(job_id)}}
        assert _get_current_worker_job_id(worker) == job_id

    @pytest.mark.parametrize(
        "labels",
        [
            pytest.param(None, id="no-labels"),
            pytest.param({}, id="empty-labels"),
            pytest.param({"team": "ml"}, id="other-labels"),
            pytest.param({_JOB_ID_LABEL: ""}, id="empty-label"),
        ],
    )
    def test_returns_none_without_label(self, labels: Optional[dict[str, str]]):
        assert (
            _get_current_worker_job_id(_router_entry("1", "http://10.0.0.1:8000", labels)) is None
        )

    def test_returns_none_on_unparsable_label(self, caplog: pytest.LogCaptureFixture):
        worker = _router_entry("1", "http://10.0.0.1:8000", {_JOB_ID_LABEL: "not-a-uuid"})
        assert _get_current_worker_job_id(worker) is None
        assert "Unparsable dstack job id worker label: 'not-a-uuid'" in caplog.text


@pytest.mark.asyncio
class TestGetRouterWorkers:
    """
    `[]` must mean "the router really has no workers", so every response that does not carry a
    usable worker list has to come back as `None`. Otherwise the caller reconciles against a
    fabricated empty list and re-adds every worker, see
    https://github.com/dstackai/dstack/issues/4300.
    """

    async def test_returns_workers(self):
        payload = {
            "workers": [
                {
                    "id": "1",
                    "url": "http://10.0.0.1:8000",
                    "labels": {_JOB_ID_LABEL: "a7d1c5a4-5d53-4d7e-a4ad-2a6c4e1f3e0b"},
                    "worker_type": "regular",
                    "is_healthy": True,
                },
                # The router omits empty labels
                {"id": "2", "url": "grpc://10.0.0.2:8000", "worker_type": "regular"},
            ],
            "total": 2,
            "stats": {"prefill_count": 0, "decode_count": 0, "regular_count": 2},
        }
        async with _mock_client(lambda _: httpx.Response(200, json=payload)) as client:
            assert await _get_router_workers(client, log_prefix="Router") == [
                {
                    "id": "1",
                    "url": "http://10.0.0.1:8000",
                    "labels": {_JOB_ID_LABEL: "a7d1c5a4-5d53-4d7e-a4ad-2a6c4e1f3e0b"},
                },
                {"id": "2", "url": "grpc://10.0.0.2:8000"},
            ]

    async def test_returns_empty_list_when_router_has_no_workers(self):
        async with _mock_client(lambda _: httpx.Response(200, json={"workers": []})) as client:
            assert await _get_router_workers(client, log_prefix="Router") == []

    @pytest.mark.parametrize(
        "response",
        [
            pytest.param(httpx.Response(500, json={"workers": []}), id="unexpected-status"),
            pytest.param(httpx.Response(200, content=b"not json"), id="unparsable"),
            pytest.param(httpx.Response(200, json=["a"]), id="not-an-object"),
            pytest.param(httpx.Response(200, json={}), id="no-workers"),
            pytest.param(httpx.Response(200, json={"workers": "oops"}), id="not-an-array"),
            pytest.param(
                httpx.Response(200, json={"workers": [{"url": "http://10.0.0.1:8000"}]}),
                id="worker-without-id",
            ),
            pytest.param(
                httpx.Response(
                    200,
                    json={"workers": [{"id": "1", "url": "http://10.0.0.1", "labels": {"a": 1}}]},
                ),
                id="worker-with-invalid-labels",
            ),
            pytest.param(
                httpx.Response(
                    200, json={"workers": [{"id": str(i), "url": "u"} for i in range(8193)]}
                ),
                id="too-many-workers",
            ),
        ],
    )
    async def test_returns_none_on_unusable_response(self, response: httpx.Response):
        async with _mock_client(lambda _: response) as client:
            assert await _get_router_workers(client, log_prefix="Router") is None

    @pytest.mark.parametrize("with_content_length", [True, False])
    async def test_returns_none_when_response_too_large(
        self, caplog: pytest.LogCaptureFixture, with_content_length: bool
    ):
        def handler(request: httpx.Request) -> httpx.Response:
            if with_content_length:
                return httpx.Response(200, content=b" " * (2 * 1024 * 1024 + 1))
            return httpx.Response(200, content=_chunks(b" " * 1024 * 1024, count=3))

        async with _mock_client(handler) as client:
            assert await _get_router_workers(client, log_prefix="Router") is None
        assert "Router: GET /workers: response too large" in caplog.text

    async def test_returns_none_on_request_error(self, caplog: pytest.LogCaptureFixture):
        def handler(request: httpx.Request) -> httpx.Response:
            # What an SSH tunnel to a port nobody listens on yet produces.
            raise httpx.ReadError("")

        caplog.set_level(level=logging.DEBUG, logger=router_worker_sync.__name__)
        async with _mock_client(handler) as client:
            assert await _get_router_workers(client, log_prefix="Router") is None
        # A router that has not bound its port yet is expected, not an error.
        assert "Router: GET /workers: request failed" in caplog.text
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
                    "labels": {_JOB_ID_LABEL: "a7d1c5a4-5d53-4d7e-a4ad-2a6c4e1f3e0b"},
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
                    "labels": {_JOB_ID_LABEL: "a7d1c5a4-5d53-4d7e-a4ad-2a6c4e1f3e0b"},
                },
                id="grpc-prefill",
            ),
        ],
    )
    async def test_posts_worker_as_is(
        self, caplog: pytest.LogCaptureFixture, worker: _TargetWorker
    ):
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(202, json={"status": "accepted", "worker_id": "1"})

        async with _mock_client(handler) as client:
            await _add_worker_to_router(client, log_prefix="Router", worker=worker)

        assert len(requests) == 1
        assert requests[0].method == "POST"
        assert requests[0].url.path == "/workers"
        assert json.loads(requests[0].content) == worker
        assert not [r for r in caplog.records if r.levelno > logging.DEBUG]

    @pytest.mark.parametrize("code", ["WORKER_CREATE_IN_PROGRESS", "WORKER_ALREADY_EXISTS"])
    async def test_accepts_conflict_with_same_worker(
        self, caplog: pytest.LogCaptureFixture, code: str
    ):
        # The router registers workers asynchronously, so a sync may add one again before
        # the router lists it
        response = httpx.Response(409, json={"error": "conflict", "code": code})
        async with _mock_client(lambda _: response) as client:
            await _add_worker_to_router(client, log_prefix="Router", worker=_http_worker(0))
        assert not [r for r in caplog.records if r.levelno > logging.DEBUG]

    @pytest.mark.parametrize(
        ["response", "message"],
        [
            pytest.param(
                httpx.Response(202, json={"status": "rejected", "worker_id": "1"}),
                "unexpected accepted status: rejected",
                id="not-accepted",
            ),
            pytest.param(
                httpx.Response(202, json={"status": "accepted"}),
                "accepted response validation failed",
                id="invalid-accepted",
            ),
            pytest.param(
                httpx.Response(409, json={"error": "conflict", "code": "OTHER"}),
                "unexpected conflict code: OTHER",
                id="unexpected-conflict",
            ),
            pytest.param(
                httpx.Response(409, json={}),
                "conflict response validation failed",
                id="invalid-conflict",
            ),
            pytest.param(
                httpx.Response(500, content=b"boom"),
                "unexpected status code: 500: b'boom'",
                id="unexpected-status",
            ),
        ],
    )
    async def test_warns_on_unexpected_response(
        self, caplog: pytest.LogCaptureFixture, response: httpx.Response, message: str
    ):
        async with _mock_client(lambda _: response) as client:
            await _add_worker_to_router(client, log_prefix="Router", worker=_http_worker(0))
        assert f"Router: POST /workers: http://{_worker_address(0)}: {message}" in caplog.text


@pytest.mark.asyncio
class TestRemoveWorkerFromRouter:
    async def test_deletes_worker_by_id(self, caplog: pytest.LogCaptureFixture):
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(202, json={"status": "accepted", "worker_id": "w1"})

        async with _mock_client(handler) as client:
            await _remove_worker_from_router(client, log_prefix="Router", worker_id="w1")

        assert [(r.method, r.url.path) for r in requests] == [("DELETE", "/workers/w1")]
        assert not [r for r in caplog.records if r.levelno > logging.DEBUG]

    async def test_logs_truncated_body_on_unexpected_status(
        self, caplog: pytest.LogCaptureFixture
    ):
        response = httpx.Response(500, content=b"x" * 2000)
        async with _mock_client(lambda _: response) as client:
            await _remove_worker_from_router(client, log_prefix="Router", worker_id="w1")
        assert "Router: DELETE /workers/w1: unexpected status code: 500:" in caplog.text
        assert f"b'{'x' * 1024}'... (2000 bytes total)" in caplog.text
        assert "x" * 1025 not in caplog.text


@pytest.mark.asyncio
class TestProbeHttpWorker:
    """
    The probe talks to the replica over the tunnel, but the `url` it reports is the address the
    router dials.
    """

    @pytest.mark.parametrize(
        ["server_info", "expected"],
        [
            pytest.param(
                {"status": "ready"},
                {"worker_type": "regular"},
                id="regular",
            ),
            pytest.param(
                {
                    "status": "ready",
                    "disaggregation_mode": "prefill",
                    "disaggregation_bootstrap_port": 8998,
                },
                {"worker_type": "prefill", "bootstrap_port": 8998},
                id="prefill",
            ),
            pytest.param(
                {"status": "ready", "disaggregation_mode": "decode"},
                {"worker_type": "decode"},
                id="decode",
            ),
        ],
    )
    async def test_reports_worker(self, server_info: dict, expected: dict):
        async with _mock_client(lambda _: httpx.Response(200, json=server_info)) as client:
            worker = await _probe_http_worker(client, log_prefix="Worker", address="10.0.0.1:8000")
        assert worker == {
            "url": "http://10.0.0.1:8000",
            "connection_mode": "http",
            "runtime_type": "sglang",
            **expected,
        }

    async def test_returns_none_when_not_ready(self):
        response = httpx.Response(200, json={"status": "starting"})
        async with _mock_client(lambda _: response) as client:
            assert (
                await _probe_http_worker(client, log_prefix="Worker", address="10.0.0.1:8000")
                is None
            )

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param(b"not json", id="not-json"),
            # Detected as UTF-16 by its BOM, but not valid UTF-16
            pytest.param(b"\xff\xfe\xfa", id="not-text"),
        ],
    )
    async def test_returns_none_on_unparsable_body(
        self, caplog: pytest.LogCaptureFixture, body: bytes
    ):
        async with _mock_client(lambda _: httpx.Response(200, content=body)) as client:
            assert (
                await _probe_http_worker(client, log_prefix="Worker", address="10.0.0.1:8000")
                is None
            )
        assert (
            "Worker: http://10.0.0.1:8000: GET /server_info: response parsing failed"
            in caplog.text
        )

    async def test_returns_none_on_unexpected_status(self, caplog: pytest.LogCaptureFixture):
        async with _mock_client(lambda _: httpx.Response(404)) as client:
            assert (
                await _probe_http_worker(client, log_prefix="Worker", address="10.0.0.1:8000")
                is None
            )
        assert "GET /server_info: unexpected status code: 404" in caplog.text

    async def test_returns_none_on_request_error(self, caplog: pytest.LogCaptureFixture):
        caplog.set_level(level=logging.DEBUG, logger=router_worker_sync.__name__)
        async with _mock_client(_grpc_server_http_handler) as client:
            assert (
                await _probe_http_worker(client, log_prefix="Worker", address="10.0.0.1:8000")
                is None
            )
        # Repeats every sync until the worker is up, or forever if it is a gRPC worker, so it
        # must not be logged as an error, see https://github.com/dstackai/dstack/issues/4300.
        assert "GET /server_info: request failed" in caplog.text
        assert not [r for r in caplog.records if r.levelno > logging.DEBUG]


@pytest.mark.asyncio
class TestProbeSglangGrpcWorker:
    @pytest.mark.parametrize(
        ["server_args", "expected"],
        [
            pytest.param(
                {"disaggregation_mode": "null"},
                {"worker_type": "regular"},
                id="regular",
            ),
            pytest.param(
                {"disaggregation_mode": "prefill", "disaggregation_bootstrap_port": 8998},
                {"worker_type": "prefill", "bootstrap_port": 8998},
                id="prefill",
            ),
            pytest.param(
                {"disaggregation_mode": "decode"},
                {"worker_type": "decode"},
                id="decode",
            ),
        ],
    )
    async def test_reports_worker(self, server_args: dict, expected: dict):
        response = sglang_scheduler_pb2.GetServerInfoResponse(server_args=server_args)
        channel = _FakeGrpcChannel({_SGLANG_GET_SERVER_INFO: response})

        worker = await _probe_sglang_grpc_worker(
            channel, log_prefix="Worker", address="10.0.0.1:8000"
        )

        expected = {
            "url": "grpc://10.0.0.1:8000",
            "connection_mode": "grpc",
            "runtime_type": "sglang",
            **expected,
        }
        # Compared as sent to the router: `server_args` is a `Struct`, which has only float
        # numbers, and `8998.0 == 8998`, but the router expects an integer port
        assert json.dumps(worker, sort_keys=True) == json.dumps(expected, sort_keys=True)

    @pytest.mark.parametrize(
        "code",
        [
            # Not listening yet, or an HTTP worker
            grpc.StatusCode.UNAVAILABLE,
            grpc.StatusCode.DEADLINE_EXCEEDED,
            # A vLLM worker
            grpc.StatusCode.UNIMPLEMENTED,
            grpc.StatusCode.CANCELLED,
        ],
    )
    async def test_returns_none_on_expected_error(
        self, caplog: pytest.LogCaptureFixture, code: grpc.StatusCode
    ):
        caplog.set_level(level=logging.DEBUG, logger=router_worker_sync.__name__)
        channel = _FakeGrpcChannel({_SGLANG_GET_SERVER_INFO: _rpc_error(code)})
        assert (
            await _probe_sglang_grpc_worker(channel, log_prefix="Worker", address="10.0.0.1:8000")
            is None
        )
        assert not [r for r in caplog.records if r.levelno > logging.DEBUG]

    async def test_warns_on_unexpected_error(self, caplog: pytest.LogCaptureFixture):
        channel = _FakeGrpcChannel(
            {_SGLANG_GET_SERVER_INFO: _rpc_error(grpc.StatusCode.PERMISSION_DENIED)}
        )
        assert (
            await _probe_sglang_grpc_worker(channel, log_prefix="Worker", address="10.0.0.1:8000")
            is None
        )
        assert (
            "Worker: grpc://10.0.0.1:8000: sglang probe failed: StatusCode.PERMISSION_DENIED"
            in caplog.text
        )


@pytest.mark.asyncio
class TestProbeVllmGrpcWorker:
    @pytest.mark.parametrize(
        ["kv_role", "kv_connector", "expected"],
        [
            pytest.param("", "", {"worker_type": "regular"}, id="regular"),
            pytest.param(
                "kv_both",
                "NixlConnector",
                {"worker_type": "regular", "kv_role": "kv_both", "kv_connector": "NixlConnector"},
                id="kv-both",
            ),
            pytest.param(
                "kv_producer",
                "NixlConnector",
                {
                    "worker_type": "prefill",
                    "kv_role": "kv_producer",
                    "kv_connector": "NixlConnector",
                },
                id="prefill",
            ),
            pytest.param(
                "kv_consumer",
                "NixlConnector",
                {
                    "worker_type": "decode",
                    "kv_role": "kv_consumer",
                    "kv_connector": "NixlConnector",
                },
                id="decode",
            ),
        ],
    )
    async def test_reports_worker(self, kv_role: str, kv_connector: str, expected: dict):
        response = vllm_engine_pb2.GetServerInfoResponse(
            kv_role=kv_role, kv_connector=kv_connector
        )
        channel = _FakeGrpcChannel({_VLLM_GET_SERVER_INFO: response})

        worker = await _probe_vllm_grpc_worker(
            channel, log_prefix="Worker", address="10.0.0.1:8000"
        )

        assert worker == {
            "url": "grpc://10.0.0.1:8000",
            "connection_mode": "grpc",
            "runtime_type": "vllm",
            **expected,
        }

    @pytest.mark.parametrize(
        "code",
        [
            # Not listening yet, or an HTTP worker
            grpc.StatusCode.UNAVAILABLE,
            grpc.StatusCode.DEADLINE_EXCEEDED,
            # An SGLang worker
            grpc.StatusCode.UNIMPLEMENTED,
            grpc.StatusCode.CANCELLED,
        ],
    )
    async def test_returns_none_on_expected_error(
        self, caplog: pytest.LogCaptureFixture, code: grpc.StatusCode
    ):
        caplog.set_level(level=logging.DEBUG, logger=router_worker_sync.__name__)
        channel = _FakeGrpcChannel({_VLLM_GET_SERVER_INFO: _rpc_error(code)})
        assert (
            await _probe_vllm_grpc_worker(channel, log_prefix="Worker", address="10.0.0.1:8000")
            is None
        )
        assert not [r for r in caplog.records if r.levelno > logging.DEBUG]

    async def test_warns_on_unexpected_error(self, caplog: pytest.LogCaptureFixture):
        channel = _FakeGrpcChannel(
            {_VLLM_GET_SERVER_INFO: _rpc_error(grpc.StatusCode.PERMISSION_DENIED)}
        )
        assert (
            await _probe_vllm_grpc_worker(channel, log_prefix="Worker", address="10.0.0.1:8000")
            is None
        )
        assert (
            "Worker: grpc://10.0.0.1:8000: vllm probe failed: StatusCode.PERMISSION_DENIED"
            in caplog.text
        )


def _service_configuration() -> ServiceConfiguration:
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
    assert isinstance(conf, ServiceConfiguration)
    return conf


async def _create_router_service_run(
    session: AsyncSession, *, router_count: int = 1, worker_count: int = 0
) -> tuple[RunModel, list[JobModel], list[JobModel]]:
    """
    Creates a running service run with running router and worker jobs. Worker `i` listens on
    `_worker_address(i)`.

    Returns:
        The run, its router jobs, and its worker jobs.
    """
    project = await create_project(session=session)
    user = await create_user(session=session)
    repo = await create_repo(session=session, project_id=project.id)
    run = await create_run(
        session=session,
        project=project,
        repo=repo,
        user=user,
        status=RunStatus.RUNNING,
        run_spec=get_run_spec(
            repo_id=repo.name, run_name="test-run", configuration=_service_configuration()
        ),
    )
    # More than one running router means a rolling deployment is replacing the router
    router_jobs = [
        await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            replica_num=replica_num,
            replica_group_name="router",
        )
        for replica_num in range(router_count)
    ]
    worker_jobs = [
        await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            replica_num=router_count + i,
            replica_group_name="worker",
            job_provisioning_data=get_job_provisioning_data(internal_ip=f"10.0.0.{i + 1}"),
        )
        for i in range(worker_count)
    ]
    await session.refresh(run, attribute_names=["jobs"])
    return run, router_jobs, worker_jobs


def _worker_address(index: int) -> str:
    return f"10.0.0.{index + 1}:8000"


def _http_worker(index: int) -> _TargetWorker:
    return {
        "url": f"http://{_worker_address(index)}",
        "worker_type": "regular",
        "connection_mode": "http",
        "runtime_type": "sglang",
    }


def _job_id_label(job: JobModel) -> dict[str, str]:
    return {_JOB_ID_LABEL: str(job.id)}


def _router_entry(worker_id: str, url: str, labels: Optional[dict[str, str]] = None) -> dict:
    """A worker as listed by the router `GET /workers`, with the fields the sync reads"""
    entry: dict = {"id": worker_id, "url": url}
    if labels is not None:
        entry["labels"] = labels
    return entry


class _FakeRouter:
    """An in-memory router `/workers` API that counts the connections made to it"""

    def __init__(
        self,
        workers: Optional[list[dict]] = None,
        *,
        connect_error: Optional[Exception] = None,
        update_error: Optional[Exception] = None,
    ):
        self.workers = list(workers or [])
        self.connect_error = connect_error
        self.update_error = update_error
        self.connections = 0
        self.added: list[dict] = []
        self.removed_ids: list[str] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/workers":
            return httpx.Response(200, json={"workers": self.workers, "total": len(self.workers)})
        if self.update_error is not None:
            raise self.update_error
        if request.method == "POST" and request.url.path == "/workers":
            worker = json.loads(request.content)
            worker_id = f"added-{len(self.added)}"
            self.added.append(worker)
            self.workers.append({"id": worker_id, **worker})
            return httpx.Response(202, json={"status": "accepted", "worker_id": worker_id})
        if request.method == "DELETE" and request.url.path.startswith("/workers/"):
            worker_id = request.url.path.removeprefix("/workers/")
            self.removed_ids.append(worker_id)
            self.workers = [w for w in self.workers if w["id"] != worker_id]
            return httpx.Response(202, json={"status": "accepted", "worker_id": worker_id})
        return httpx.Response(404)


@contextmanager
def _fake_router_replicas(routers: dict[uuid.UUID, _FakeRouter]) -> Iterator[None]:
    """Route each router job's client to its fake router, keyed by the job id"""

    @asynccontextmanager
    async def get_service_replica_client(job: JobModel) -> AsyncIterator[AsyncClient]:
        router = routers[job.id]
        router.connections += 1
        if router.connect_error is not None:
            raise router.connect_error
        async with _mock_client(router.handle) as client:
            yield client

    with patch.object(
        router_worker_sync, "get_service_replica_client", get_service_replica_client
    ):
        yield


@contextmanager
def _fake_worker_probes(workers: Mapping[str, _TargetWorker]) -> Iterator[AsyncMock]:
    """Patch probing so that the worker replica at each address reports the given worker"""

    async def probe(job: JobModel, *, address: str) -> Optional[_TargetWorker]:
        # A copy, as the sync labels the reported worker in place
        return copy.deepcopy(workers.get(address))

    with patch.object(
        router_worker_sync, "_probe_worker_replica", new_callable=AsyncMock, side_effect=probe
    ) as probe_mock:
        yield probe_mock


def _job() -> JobModel:
    return JobModel(id=uuid.uuid4(), job_name="test-run-0-1")


@contextmanager
def _fake_replica_transports(
    *,
    http_handler: Optional[Callable[[httpx.Request], httpx.Response]] = None,
    grpc_channel: Optional["_FakeGrpcChannel"] = None,
    tunnel_error: Optional[Exception] = None,
) -> Iterator[None]:
    """Patch the tunnel to a worker replica and the HTTP client and gRPC channel over it"""

    @asynccontextmanager
    async def get_tunnel(job: JobModel) -> AsyncIterator[Path]:
        if tunnel_error is not None:
            raise tunnel_error
        yield Path("replica.sock")

    @asynccontextmanager
    async def get_http_client(uds_path: Path) -> AsyncIterator[AsyncClient]:
        assert http_handler is not None
        async with _mock_client(http_handler) as client:
            yield client

    @asynccontextmanager
    async def get_grpc_channel(uds_path: Path) -> AsyncIterator["_FakeGrpcChannel"]:
        assert grpc_channel is not None
        yield grpc_channel

    with (
        patch.object(router_worker_sync, "get_service_replica_tunnel", get_tunnel),
        patch.object(
            router_worker_sync, "get_service_replica_http_client_over_uds", get_http_client
        ),
        patch.object(
            router_worker_sync, "get_service_replica_grpc_channel_over_uds", get_grpc_channel
        ),
    ):
        yield


def _grpc_server_http_handler(request: httpx.Request) -> httpx.Response:
    # What an HTTP/1.1 request to an HTTP/2-only gRPC server produces
    raise httpx.RemoteProtocolError("illegal request line")


class _FakeGrpcChannel:
    """
    A channel to a gRPC worker replica that serves the given unary methods. The probes create
    real stubs on it, so a stub of a service the worker doesn't serve fails as UNIMPLEMENTED,
    as against a real worker.
    """

    def __init__(
        self,
        responses: Optional[Mapping[str, Union[Message, grpc.aio.AioRpcError]]] = None,
        *,
        unknown_method_code: grpc.StatusCode = grpc.StatusCode.UNIMPLEMENTED,
        hang: bool = False,
    ):
        self.responses = responses or {}
        self.unknown_method_code = unknown_method_code
        self.hang = hang
        """Whether calls never complete, only cancellation ends them"""
        self.cancelled: list[str] = []
        """Methods whose calls were cancelled"""

    def unary_unary(self, method: str, request_serializer, response_deserializer, **kwargs):
        async def call(request, **kwargs):
            if self.hang:
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    self.cancelled.append(method)
                    raise
            response = self.responses.get(method)
            if response is None:
                raise _rpc_error(self.unknown_method_code)
            if isinstance(response, grpc.aio.AioRpcError):
                raise response
            # Through the wire format, as the real stub would receive it
            return response_deserializer(response.SerializeToString())

        return call

    def unary_stream(self, *args, **kwargs):
        # Stubs create all their methods, but the probes only call unary ones
        return None


def _rpc_error(code: grpc.StatusCode) -> grpc.aio.AioRpcError:
    return grpc.aio.AioRpcError(code, grpc.aio.Metadata(), grpc.aio.Metadata(), details=code.name)


def _mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> AsyncClient:
    return AsyncClient(transport=httpx.MockTransport(handler))


async def _chunks(chunk: bytes, *, count: int) -> AsyncIterator[bytes]:
    for _ in range(count):
        yield chunk
