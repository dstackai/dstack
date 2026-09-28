"""Reconcile SGLang router /workers with dstack's ready worker replicas (async, SSH-tunneled)."""

import json
from dataclasses import dataclass
from typing import Any, List, Literal, Optional, TypedDict
from urllib.parse import urlsplit, urlunsplit

import grpc
from google.protobuf.json_format import MessageToDict
from httpx import AsyncClient, RequestError, Response
from smg_grpc_proto import (
    sglang_scheduler_pb2,
    sglang_scheduler_pb2_grpc,
    vllm_engine_pb2,
    vllm_engine_pb2_grpc,
)
from typing_extensions import NotRequired

from dstack._internal.core.errors import SSHError
from dstack._internal.core.models.common import validate_json_extra_ignore
from dstack._internal.core.models.configurations import ReplicaGroup, ServiceConfiguration
from dstack._internal.core.models.runs import JobStatus, RunSpec, get_service_port
from dstack._internal.server.models import JobModel, RunModel
from dstack._internal.server.services.jobs import get_job_provisioning_data, get_job_spec
from dstack._internal.server.services.jobs.job_replica_grpc_client import (
    get_service_replica_grpc_channel_over_uds,
)
from dstack._internal.server.services.jobs.job_replica_http_client import (
    get_service_replica_client,
    get_service_replica_http_client_over_uds,
)
from dstack._internal.server.services.jobs.job_replica_tunnel import get_service_replica_tunnel
from dstack._internal.server.services.logging import fmt
from dstack._internal.utils.logging import get_logger

from .replicas import job_belongs_to_group
from .service_router_worker_sync import run_spec_has_sglang_router_replica_group

logger = get_logger(__name__)

# Requests are made over a UDS tunnel to the replica, so the authority is a placeholder.
_HTTP_BASE_URL = "http://dstack"
_HTTP_TIMEOUT = 10.0
_MAX_SERVER_INFO_RESPONSE_BYTES = 256 * 1024
_MAX_WORKERS_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_WORKERS_COMMAND_ACK_BYTES = 64 * 1024
_MAX_WORKERS_LIST_ITEMS = 8192
_GRPC_TIMEOUT = 30.0


class _ResponseTooLargeError(Exception):
    pass


async def _stream_response_body_bytes(resp: Response, max_bytes: int) -> bytes:
    buf = bytearray()
    async for chunk in resp.aiter_bytes():
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise _ResponseTooLargeError()
    return bytes(buf)


async def _request_json_limited(
    client: AsyncClient,
    method: str,
    url: str,
    *,
    max_response_bytes: int,
    ok_statuses: set[int],
    json_body: Optional[dict] = None,
    timeout: float = _HTTP_TIMEOUT,
) -> Any:
    kwargs: dict[str, Any] = {"timeout": timeout}
    if json_body is not None:
        kwargs["json"] = json_body
    endpoint = f"{method} {url}"
    async with client.stream(method, url, **kwargs) as resp:
        if resp.status_code not in ok_statuses:
            logger.warning(
                "router_http unexpected status endpoint=%s status_code=%s expected=%s",
                endpoint,
                resp.status_code,
                sorted(ok_statuses),
            )
            return None
        cl = resp.headers.get("content-length")
        if cl is not None:
            try:
                if int(cl) > max_response_bytes:
                    raise _ResponseTooLargeError()
            except ValueError:
                pass
        raw = await _stream_response_body_bytes(resp, max_response_bytes)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("router_http JSON parse failed endpoint=%s", endpoint)
        return None


# https://github.com/smg-project/smg/blob/3be823a700fabaff3add8a390cf78f163479d686/crates/protocols/src/worker.rs#L601
# Only fields used to register a worker (POST /workers) are included
class _TargetWorker(TypedDict):
    url: str
    worker_type: "_WorkerType"
    connection_mode: "_ConnectionMode"
    runtime_type: "_RuntimeType"
    bootstrap_port: NotRequired[int]
    kv_connector: NotRequired[str]
    kv_role: NotRequired[str]


# https://github.com/smg-project/smg/blob/3be823a700fabaff3add8a390cf78f163479d686/crates/protocols/src/worker.rs#L29
# Only types we support are included
_WorkerType = Literal["regular", "prefill", "decode"]

# https://github.com/smg-project/smg/blob/3be823a700fabaff3add8a390cf78f163479d686/crates/protocols/src/worker.rs#L76
# Only modes we support are included
_ConnectionMode = Literal["http", "grpc"]
# The order does matter -- we discover connection modes in the specified order
_CONNECTION_MODES: tuple[_ConnectionMode, ...] = ("http", "grpc")

# https://github.com/smg-project/smg/blob/3be823a700fabaff3add8a390cf78f163479d686/crates/protocols/src/worker.rs#L227
# Only types we support are included
_RuntimeType = Literal["sglang", "vllm"]
# The order does matter -- we discover runtime types in the specified order
_RUNTIME_TYPES: tuple[_RuntimeType, ...] = ("sglang", "vllm")


def run_model_has_sglang_router_replica_group(run_model: RunModel) -> bool:
    run_spec = validate_json_extra_ignore(RunSpec, run_model.run_spec)
    return run_spec_has_sglang_router_replica_group(run_spec)


def _get_router_jobs(run_model: RunModel, router_group: ReplicaGroup) -> List[JobModel]:
    group_name = router_group.name
    assert group_name is not None, "Replica group name is set by validation"
    # The router group is validated to have `replicas: 1`, but a rolling deployment runs the
    # replacement router alongside the old one until the old one is scaled down. Every running
    # router is synced, otherwise the replacement has no workers until the old one is gone.
    return [
        j
        for j in run_model.jobs
        if job_belongs_to_group(j, group_name) and j.status == JobStatus.RUNNING
    ]


def _normalize_worker_url(url: str) -> str:
    url = url.strip()
    parts = urlsplit(url)
    path = (parts.path or "").rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def _get_connection_mode_from_workers(
    current_workers: List[dict],
) -> Optional[_ConnectionMode]:
    # PD services register multiple workers (e.g. prefill and decode). We expect
    # every listed worker to use the same connection_mode (all grpc or all http),
    # not a mix of protocols on one router.
    modes: set[str] = set()
    for worker in current_workers:
        mode = worker.get("connection_mode")
        if isinstance(mode, str) and mode in ("http", "grpc"):
            modes.add(mode)
    if modes == {"grpc"}:
        return "grpc"
    if modes == {"http"}:
        return "http"
    return None


def _get_runtime_type_from_workers(
    current_workers: List[dict],
) -> Optional[_RuntimeType]:
    # We expect every listed gRPC worker to share the same runtime_type
    # (all sglang or all vllm), not a mix of runtimes on one router.
    runtimes: set[str] = set()
    for worker in current_workers:
        # For HTTP workers,there is no “pick vLLM vs SGLang gRPC stub” step,
        # so runtime_type is irrelevant for HTTP workers.
        if worker.get("connection_mode") != "grpc":
            continue
        runtime_type = worker.get("runtime_type")
        if isinstance(runtime_type, str) and runtime_type in _RUNTIME_TYPES:
            runtimes.add(runtime_type)
    if runtimes == {"sglang"}:
        return "sglang"
    if runtimes == {"vllm"}:
        return "vllm"
    return None


async def _get_router_workers(client: AsyncClient) -> Optional[List[dict]]:
    try:
        data = await _request_json_limited(
            client,
            "GET",
            f"{_HTTP_BASE_URL}/workers",
            max_response_bytes=_MAX_WORKERS_RESPONSE_BYTES,
            ok_statuses={200},
        )
        if not isinstance(data, dict):
            # Non-200 status or unparsable response or response is not a JSON object
            return None
        workers = data.get("workers")
        if not isinstance(workers, list):
            # Unexpected response structure -- `workers` is missing or is not an array
            return None
        # TODO: Truncating a long list and/or dropping unexpectedly shaped items doesn't seem
        # right. We should add validation (an item must be a dict with some required fields, see
        # _get_workers_diff) and decide what to do with a partially valid list
        if len(workers) > _MAX_WORKERS_LIST_ITEMS:
            logger.warning(
                "Router /workers list exceeds %s items, truncating",
                _MAX_WORKERS_LIST_ITEMS,
            )
            workers = workers[:_MAX_WORKERS_LIST_ITEMS]
        return [w for w in workers if isinstance(w, dict)]
    except _ResponseTooLargeError:
        logger.warning("Router /workers response exceeded size limit")
    except RequestError as e:
        logger.debug("Router /workers not ready yet: %r", e)
    return None


async def _add_worker_to_router(client: AsyncClient, worker: _TargetWorker) -> bool:
    url = worker["url"]
    try:
        body = await _request_json_limited(
            client,
            "POST",
            f"{_HTTP_BASE_URL}/workers",
            max_response_bytes=_MAX_WORKERS_COMMAND_ACK_BYTES,
            ok_statuses={202},
            json_body=dict(worker),
        )
        added = isinstance(body, dict) and body.get("status") == "accepted"
        if not added:
            logger.warning("Unexpected add-worker response for %s: %s", url, body)
        return added
    except _ResponseTooLargeError:
        logger.warning("Router add-worker response exceeded size limit for %s", url)
    except RequestError as e:
        logger.warning("Error adding worker %s: %r", url, e)
    return False


async def _remove_worker_from_router_by_id(
    client: AsyncClient, worker_id: str, *, worker_url: str
) -> bool:
    try:
        body = await _request_json_limited(
            client,
            "DELETE",
            f"{_HTTP_BASE_URL}/workers/{worker_id}",
            max_response_bytes=_MAX_WORKERS_COMMAND_ACK_BYTES,
            ok_statuses={202},
        )
        removed = isinstance(body, dict) and body.get("status") == "accepted"
        if not removed:
            logger.warning("Unexpected remove-worker response for %s: %s", worker_url, body)
        return removed
    except _ResponseTooLargeError:
        logger.warning("Router remove-worker response exceeded size limit for %s", worker_url)
    except RequestError as e:
        logger.warning("Error removing worker %s: %r", worker_url, e)
    return False


@dataclass
class _WorkersDiff:
    to_add: List[_TargetWorker]
    to_remove: dict[str, Optional[str]]
    """Normalized worker URL to the router's worker id, `None` if the router reported none"""

    def is_empty(self) -> bool:
        return not self.to_add and not self.to_remove


def _get_workers_diff(
    target_workers: List[_TargetWorker], current_workers: List[dict]
) -> _WorkersDiff:
    current_ids_by_norm_url: dict[str, Optional[str]] = {}
    for w in current_workers:
        u = w.get("url")
        if not isinstance(u, str) or not u:
            continue
        norm_u = _normalize_worker_url(u)
        wid = w.get("id")
        if isinstance(wid, str) and wid:
            current_ids_by_norm_url[norm_u] = wid
        else:
            current_ids_by_norm_url.setdefault(norm_u, None)
    target_by_norm_url = {_normalize_worker_url(t["url"]): t for t in target_workers}
    to_add = sorted(target_by_norm_url.keys() - current_ids_by_norm_url.keys())
    to_remove = sorted(current_ids_by_norm_url.keys() - target_by_norm_url.keys())
    return _WorkersDiff(
        to_add=[target_by_norm_url[u] for u in to_add],
        to_remove={u: current_ids_by_norm_url[u] for u in to_remove},
    )


async def _apply_workers_diff(
    client: AsyncClient, diff: _WorkersDiff, *, router_job: JobModel
) -> None:
    for worker in diff.to_add:
        if not await _add_worker_to_router(client, worker):
            logger.debug(
                "%s: failed to add worker %s, continuing with others",
                fmt(router_job),
                worker["url"],
            )
    for url, worker_id in diff.to_remove.items():
        if worker_id is None:
            logger.error("%s: no worker id found for url %s", fmt(router_job), url)
            continue
        if not await _remove_worker_from_router_by_id(client, worker_id, worker_url=url):
            logger.debug(
                "%s: failed to remove worker %s, continuing with others", fmt(router_job), url
            )


def _vllm_kv_role_to_worker_type(kv_role: str) -> _WorkerType:
    if kv_role == "kv_producer":
        return "prefill"
    if kv_role == "kv_consumer":
        return "decode"
    return "regular"


def _is_expected_grpc_error(error: grpc.aio.AioRpcError) -> bool:
    """Expected while a gRPC worker is still starting or the wrong stub is probed."""
    return error.code() in (
        grpc.StatusCode.UNAVAILABLE,
        grpc.StatusCode.DEADLINE_EXCEEDED,
        grpc.StatusCode.UNIMPLEMENTED,
    )


async def _probe_http_worker(client: AsyncClient, *, address: str) -> Optional[_TargetWorker]:
    # The request goes over the tunnel, `worker_url` is the address the router itself dials.
    worker_url = f"http://{address}"
    try:
        data = await _request_json_limited(
            client,
            "GET",
            f"{_HTTP_BASE_URL}/server_info",
            max_response_bytes=_MAX_SERVER_INFO_RESPONSE_BYTES,
            ok_statuses={200},
        )
        if isinstance(data, dict):
            if data.get("status") != "ready":
                return None
            mode = data.get("disaggregation_mode", "")
            if mode == "prefill":
                bootstrap_port = data.get("disaggregation_bootstrap_port")
                worker: _TargetWorker = {
                    "url": worker_url,
                    "worker_type": "prefill",
                    "connection_mode": "http",
                    "runtime_type": "sglang",
                }
                if bootstrap_port is not None:
                    worker["bootstrap_port"] = bootstrap_port
                return worker
            if mode == "decode":
                return {
                    "url": worker_url,
                    "worker_type": "decode",
                    "connection_mode": "http",
                    "runtime_type": "sglang",
                }
            return {
                "url": worker_url,
                "worker_type": "regular",
                "connection_mode": "http",
                "runtime_type": "sglang",
            }
    except _ResponseTooLargeError:
        logger.warning("server_info response too large for worker %s", worker_url)
    except RequestError as e:
        logger.debug("Could not fetch server_info for worker %s: %r", worker_url, e)
    return None


async def _get_grpc_server_info(
    channel: grpc.aio.Channel,
    runtime_type: _RuntimeType,
) -> Any:
    if runtime_type == "sglang":
        stub = sglang_scheduler_pb2_grpc.SglangSchedulerStub(channel)
        request = sglang_scheduler_pb2.GetServerInfoRequest()
    else:
        stub = vllm_engine_pb2_grpc.VllmEngineStub(channel)
        request = vllm_engine_pb2.GetServerInfoRequest()
    return await stub.GetServerInfo(request, timeout=_GRPC_TIMEOUT)


def _grpc_server_info_to_worker(
    worker_url: str,
    runtime_type: _RuntimeType,
    response: Any,
) -> _TargetWorker:
    if runtime_type == "vllm":
        kv_role = response.kv_role or ""
        kv_connector = response.kv_connector or ""
        worker: _TargetWorker = {
            "url": worker_url,
            "connection_mode": "grpc",
            "runtime_type": runtime_type,
            "worker_type": _vllm_kv_role_to_worker_type(kv_role),
        }
        if kv_connector:
            worker["kv_connector"] = kv_connector
        if kv_role:
            worker["kv_role"] = kv_role
        return worker

    server_args = (
        MessageToDict(response.server_args, preserving_proto_field_name=True)
        if response.server_args is not None
        else {}
    )
    mode = server_args.get("disaggregation_mode")
    worker_type = mode if mode in ("prefill", "decode") else "regular"
    worker = {
        "url": worker_url,
        "connection_mode": "grpc",
        "runtime_type": runtime_type,
        "worker_type": worker_type,
    }
    if worker_type == "prefill":
        bootstrap_port = server_args.get("disaggregation_bootstrap_port")
        if bootstrap_port is not None:
            worker["bootstrap_port"] = int(bootstrap_port)
    return worker


async def _probe_grpc_worker(
    channel: grpc.aio.Channel,
    *,
    address: str,
    runtime_type: Optional[_RuntimeType] = None,
) -> Optional[_TargetWorker]:
    # The RPC goes over the tunnel, `worker_url` is the address the router itself dials.
    worker_url = f"grpc://{address}"
    runtime_types: tuple[_RuntimeType, ...]
    if runtime_type is None:
        # Bootstrap only: router workers list has no runtime_type yet, should try all
        runtime_types = _RUNTIME_TYPES
    else:
        runtime_types = (runtime_type,)
    for runtime_type in runtime_types:
        try:
            response = await _get_grpc_server_info(channel, runtime_type)
            break
        except grpc.aio.AioRpcError as e:
            if _is_expected_grpc_error(e):
                continue
            raise
    else:
        logger.debug("gRPC worker %s not ready (GetServerInfo)", worker_url)
        return None
    return _grpc_server_info_to_worker(worker_url, runtime_type, response)


async def _get_worker(
    job_model: JobModel,
    *,
    address: str,
    connection_mode: Optional[_ConnectionMode] = None,
    runtime_type: Optional[_RuntimeType] = None,
) -> Optional[_TargetWorker]:
    connection_modes: tuple[_ConnectionMode, ...]
    if connection_mode is None:
        # No connection_mode discovered -- should probe all
        connection_modes = _CONNECTION_MODES
    else:
        connection_modes = (connection_mode,)
    try:
        async with get_service_replica_tunnel(job_model) as uds_path:
            for connection_mode in connection_modes:
                if connection_mode == "grpc":
                    async with get_service_replica_grpc_channel_over_uds(uds_path) as channel:
                        worker = await _probe_grpc_worker(
                            channel, address=address, runtime_type=runtime_type
                        )
                elif connection_mode == "http":
                    async with get_service_replica_http_client_over_uds(uds_path) as client:
                        worker = await _probe_http_worker(client, address=address)
                if worker is not None:
                    return worker
    except SSHError as e:
        # An unreachable worker is reported as not ready rather than aborting the sync, so that
        # one dead replica cannot hold back registration of the healthy ones. The cost is that a
        # transient failure deregisters a healthy worker until the next sync re-adds it.
        # TODO: `_get_workers_diff` cannot tell "not serving" from "could not be
        # reached" -- both mean "absent from the target list", hence "remove". A third, unknown
        # outcome should be excluded from both `to_add` and `to_remove`, leaving an unreachable
        # worker as the router last saw it.
        logger.warning("%s: failed to connect to worker replica: %r", fmt(job_model), e)
    return None


async def _build_target_workers(
    run_model: RunModel,
    run_spec: RunSpec,
    replica_groups: list[ReplicaGroup],
    *,
    connection_mode: Optional[_ConnectionMode] = None,
    runtime_type: Optional[_RuntimeType] = None,
) -> List[_TargetWorker]:
    workers: List[_TargetWorker] = []
    config = run_spec.configuration
    if not isinstance(config, ServiceConfiguration):
        return workers

    for group in replica_groups:
        if group.router is not None:
            continue
        assert group.name is not None, "Replica group name is set by validation"
        group_name = group.name
        for job in run_model.jobs:
            if not job_belongs_to_group(job, group_name):
                continue
            if job.status != JobStatus.RUNNING:
                continue
            jpd = get_job_provisioning_data(job)
            if jpd is None:
                continue
            hostname = jpd.internal_ip or jpd.hostname
            if not hostname:
                continue
            job_spec = get_job_spec(job)
            port = get_service_port(job_spec, config)
            worker = await _get_worker(
                job,
                address=f"{hostname}:{port}",
                connection_mode=connection_mode,
                runtime_type=runtime_type,
            )
            if worker is not None:
                workers.append(worker)
            else:
                logger.debug("%s: worker replica not ready", fmt(job))
    return workers


async def sync_router_workers_for_run_model(run_model: RunModel) -> None:
    run_spec = validate_json_extra_ignore(RunSpec, run_model.run_spec)
    config = run_spec.configuration
    if not isinstance(config, ServiceConfiguration):
        return
    replica_groups = config.replica_groups
    router_group = next((g for g in replica_groups if g.router is not None), None)
    if router_group is None:
        return

    router_jobs = _get_router_jobs(run_model, router_group)
    if not router_jobs:
        logger.debug(
            "%s: no running router job in group %s, skipping worker sync",
            fmt(run_model),
            router_group.name,
        )
        return
    # Probing the workers may take minutes, so no router tunnel is held meanwhile. Each router
    # is read first, and connected to again only if it needs updating, which in most syncs it
    # doesn't. An unreachable router is skipped, like an unreachable worker, see `_get_worker`.
    try:
        current_workers_by_router: List[tuple[JobModel, List[dict]]] = []
        for router_job in router_jobs:
            current_workers = await _get_router_replica_workers(router_job)
            if current_workers is not None:
                current_workers_by_router.append((router_job, current_workers))
        if not current_workers_by_router:
            logger.debug(
                "%s: no router in group %s returned its workers, skipping worker sync",
                fmt(run_model),
                router_group.name,
            )
            return
        # The hints spare probing connection modes and runtime types that no registered worker
        # uses. They are taken from all routers, as a router started by a rolling deployment has
        # no workers yet, which alone would mean "probe everything".
        all_current_workers = [w for _, workers in current_workers_by_router for w in workers]
        target_workers = await _build_target_workers(
            run_model,
            run_spec,
            replica_groups,
            connection_mode=_get_connection_mode_from_workers(all_current_workers),
            runtime_type=_get_runtime_type_from_workers(all_current_workers),
        )
        for router_job, current_workers in current_workers_by_router:
            if _get_workers_diff(target_workers, current_workers).is_empty():
                continue
            await _update_workers_in_router_replica(router_job, target_workers)
    except Exception:
        logger.exception("%s: unexpected error when syncing workers with router", fmt(run_model))


async def _get_router_replica_workers(router_job: JobModel) -> Optional[List[dict]]:
    try:
        async with get_service_replica_client(router_job) as client:
            current_workers = await _get_router_workers(client)
    except SSHError as e:
        _log_router_replica_unreachable(router_job, e)
        return None
    if current_workers is None:
        logger.debug("%s: failed to get current workers from the router", fmt(router_job))
    return current_workers


async def _update_workers_in_router_replica(
    router_job: JobModel, target_workers: List[_TargetWorker]
) -> None:
    try:
        async with get_service_replica_client(router_job) as client:
            # Read again: the list this update was decided on was fetched before the workers
            # were probed, possibly minutes ago.
            current_workers = await _get_router_workers(client)
            if current_workers is None:
                logger.debug("%s: failed to get current workers from the router", fmt(router_job))
                return
            diff = _get_workers_diff(target_workers, current_workers)
            await _apply_workers_diff(client, diff, router_job=router_job)
    except SSHError as e:
        _log_router_replica_unreachable(router_job, e)


def _log_router_replica_unreachable(router_job: JobModel, error: SSHError) -> None:
    # Warning is the right level: a job only reaches `RUNNING` after the server has talked to
    # its runner over SSH, so an unreachable replica is always a regression, never a replica
    # that has not started yet.
    logger.warning("%s: failed to sync workers with router: %r", fmt(router_job), error)
