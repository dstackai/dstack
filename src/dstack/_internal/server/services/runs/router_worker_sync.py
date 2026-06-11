"""Reconcile SGLang router /workers with dstack's registered worker replicas (async, SSH-tunneled)."""

import json
from typing import Any, List, Literal, Optional, TypedDict
from urllib.parse import urlsplit, urlunsplit

import grpc
from google.protobuf.json_format import MessageToDict
from httpx import (
    AsyncClient,
    ConnectError,
    ConnectTimeout,
    ReadTimeout,
    RemoteProtocolError,
    Response,
)
from smg_grpc_proto import (
    sglang_scheduler_pb2,
    sglang_scheduler_pb2_grpc,
    vllm_engine_pb2,
    vllm_engine_pb2_grpc,
)
from typing_extensions import NotRequired

from dstack._internal.core.errors import SSHError
from dstack._internal.core.models.configurations import ReplicaGroup, ServiceConfiguration
from dstack._internal.core.models.runs import JobStatus, RunSpec, get_service_port
from dstack._internal.server.models import JobModel, RunModel
from dstack._internal.server.services.jobs import get_job_provisioning_data, get_job_spec
from dstack._internal.server.services.jobs.job_replica_grpc_client import (
    get_service_replica_grpc_client,
)
from dstack._internal.server.services.jobs.job_replica_http_client import (
    get_service_replica_client,
)
from dstack._internal.server.services.logging import fmt
from dstack._internal.utils.logging import get_logger

from .replicas import job_belongs_to_group
from .service_router_worker_sync import run_spec_has_sglang_router_replica_group

logger = get_logger(__name__)

_ROUTER_HTTP = "http://dstack"
_ROUTER_HTTP_TIMEOUT = 10.0
_MAX_SERVER_INFO_RESPONSE_BYTES = 256 * 1024
_MAX_WORKERS_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_WORKERS_COMMAND_ACK_BYTES = 64 * 1024
_MAX_WORKERS_LIST_ITEMS = 8192
_GRPC_DISCOVERY_TIMEOUT = 30.0


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
    timeout: float = _ROUTER_HTTP_TIMEOUT,
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


class _TargetWorker(TypedDict):
    url: str
    worker_type: str
    bootstrap_port: NotRequired[Optional[int]]
    connection_mode: NotRequired[str]
    runtime_type: NotRequired[str]
    kv_connector: NotRequired[str]
    kv_role: NotRequired[str]


class _WorkerPayloadResult(TypedDict):
    status: Literal["ready", "not_ready"]
    worker: Optional[_TargetWorker]


_ConnectionMode = Literal["grpc", "http"]
_RuntimeType = Literal["sglang", "vllm"]
_GRPC_RUNTIME_TYPES: tuple[_RuntimeType, ...] = ("sglang", "vllm")


def run_model_has_sglang_router_replica_group(run_model: RunModel) -> bool:
    run_spec = RunSpec.__response__.parse_raw(run_model.run_spec)
    return run_spec_has_sglang_router_replica_group(run_spec)


def _get_router_job(run_model: RunModel, router_group: ReplicaGroup) -> Optional[JobModel]:
    group_name = router_group.name
    assert group_name is not None, "Replica group name is set by validation"
    router_jobs = [
        j
        for j in run_model.jobs
        if job_belongs_to_group(j, group_name) and j.status == JobStatus.RUNNING
    ]
    if not router_jobs:
        return None
    # Router replica group is currently validated to have count=1, so we assume a single active
    # router job here. When we support multiple router replicas for HA, this should be updated
    # to handle syncing across all active router jobs.
    return router_jobs[0]


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
        if isinstance(runtime_type, str) and runtime_type in _GRPC_RUNTIME_TYPES:
            runtimes.add(runtime_type)
    if runtimes == {"sglang"}:
        return "sglang"
    if runtimes == {"vllm"}:
        return "vllm"
    return None


def _is_expected_router_workers_fetch_error(error: Exception) -> bool:
    """SMG router may not accept HTTP yet during startup."""
    if isinstance(
        error,
        (
            RemoteProtocolError,
            ConnectError,
            ConnectTimeout,
            ReadTimeout,
            TimeoutError,
        ),
    ):
        return True
    if isinstance(error, OSError) and error.errno in {61, 111}:
        return True
    return False


def _log_router_workers_fetch_failure(error: Exception) -> None:
    if _is_expected_router_workers_fetch_error(error):
        logger.debug("Router /workers not ready yet: %r", error)
        return
    logger.exception("Error getting router /workers")


async def _get_router_workers(client: AsyncClient) -> List[dict]:
    try:
        data = await _request_json_limited(
            client,
            "GET",
            f"{_ROUTER_HTTP}/workers",
            max_response_bytes=_MAX_WORKERS_RESPONSE_BYTES,
            ok_statuses={200},
        )
        if not isinstance(data, dict):
            return []
        workers = data.get("workers", [])
        if not isinstance(workers, list):
            return []
        if len(workers) > _MAX_WORKERS_LIST_ITEMS:
            logger.warning(
                "Router /workers list exceeds %s items, truncating",
                _MAX_WORKERS_LIST_ITEMS,
            )
            workers = workers[:_MAX_WORKERS_LIST_ITEMS]
        return [w for w in workers if isinstance(w, dict)]
    except _ResponseTooLargeError:
        logger.warning("Router /workers response exceeded size limit")
    except Exception as e:
        _log_router_workers_fetch_failure(e)
    return []


async def _add_worker_to_router(
    client: AsyncClient,
    url: str,
    worker_type: str = "regular",
    bootstrap_port: Optional[int] = None,
    *,
    connection_mode: Optional[str] = None,
    runtime_type: Optional[str] = None,
    kv_connector: Optional[str] = None,
    kv_role: Optional[str] = None,
) -> bool:
    try:
        payload: dict = {"url": url, "worker_type": worker_type}
        if bootstrap_port is not None:
            payload["bootstrap_port"] = bootstrap_port
        if connection_mode is not None:
            payload["connection_mode"] = connection_mode
        if runtime_type is not None:
            payload["runtime_type"] = runtime_type
        if kv_connector is not None:
            payload["kv_connector"] = kv_connector
        if kv_role is not None:
            payload["kv_role"] = kv_role
        body = await _request_json_limited(
            client,
            "POST",
            f"{_ROUTER_HTTP}/workers",
            max_response_bytes=_MAX_WORKERS_COMMAND_ACK_BYTES,
            ok_statuses={202},
            json_body=payload,
        )
        return isinstance(body, dict) and body.get("status") == "accepted"
    except _ResponseTooLargeError:
        logger.warning("Router add-worker response exceeded size limit for %s", url)
        return False
    except Exception:
        logger.exception("Error adding worker %s", url)
        return False


async def _remove_worker_from_router_by_id(
    client: AsyncClient, worker_id: str, *, worker_url: str
) -> bool:
    try:
        body = await _request_json_limited(
            client,
            "DELETE",
            f"{_ROUTER_HTTP}/workers/{worker_id}",
            max_response_bytes=_MAX_WORKERS_COMMAND_ACK_BYTES,
            ok_statuses={202},
        )
        return isinstance(body, dict) and body.get("status") == "accepted"
    except _ResponseTooLargeError:
        logger.warning("Router remove-worker response exceeded size limit for %s", worker_url)
        return False
    except Exception:
        logger.exception("Error removing worker %s", worker_url)
        return False


async def _update_workers_in_router_replica(
    client: AsyncClient,
    target_workers: List[_TargetWorker],
    *,
    current_workers: List[dict],
) -> None:
    current_urls: set[str] = set()
    current_ids_by_norm_url: dict[str, str] = {}
    for w in current_workers:
        u = w.get("url")
        if not isinstance(u, str) or not u:
            continue
        norm_u = _normalize_worker_url(u)
        current_urls.add(norm_u)
        wid = w.get("id")
        if isinstance(wid, str) and wid:
            current_ids_by_norm_url[norm_u] = wid
    target_by_norm = {_normalize_worker_url(t["url"]): t for t in target_workers}
    target_urls = set(target_by_norm.keys())
    to_add = sorted(target_urls - current_urls)
    to_remove = sorted(current_urls - target_urls)
    for norm_url in to_add:
        tw = target_by_norm[norm_url]
        ok = await _add_worker_to_router(
            client,
            tw["url"],
            tw["worker_type"],
            tw.get("bootstrap_port"),
            connection_mode=tw.get("connection_mode"),
            runtime_type=tw.get("runtime_type"),
            kv_connector=tw.get("kv_connector"),
            kv_role=tw.get("kv_role"),
        )
        if not ok:
            logger.warning("Failed to add worker %s, continuing with others", tw["url"])
    for url in to_remove:
        wid = current_ids_by_norm_url.get(url)
        if not wid:
            logger.error("No worker id found for url %s", url)
            ok = False
        else:
            ok = await _remove_worker_from_router_by_id(client, wid, worker_url=url)
        if not ok:
            logger.warning("Failed to remove worker %s, continuing with others", url)


def _vllm_kv_role_to_worker_type(kv_role: str) -> str:
    if kv_role == "kv_producer":
        return "prefill"
    if kv_role == "kv_consumer":
        return "decode"
    return "regular"


def _is_expected_grpc_discovery_error(error: Exception) -> bool:
    """Expected while a gRPC worker is still starting or the wrong stub is probed."""
    if isinstance(error, grpc.aio.AioRpcError):
        return error.code() in (
            grpc.StatusCode.UNAVAILABLE,
            grpc.StatusCode.DEADLINE_EXCEEDED,
            grpc.StatusCode.UNIMPLEMENTED,
        )
    return False


async def _get_http_worker(job_model: JobModel, *, worker_url: str) -> _WorkerPayloadResult:
    try:
        async with get_service_replica_client(job_model) as client:
            data = await _request_json_limited(
                client,
                "GET",
                f"{_ROUTER_HTTP}/server_info",
                max_response_bytes=_MAX_SERVER_INFO_RESPONSE_BYTES,
                ok_statuses={200},
            )
            if isinstance(data, dict):
                if data.get("status") != "ready":
                    return {"status": "not_ready", "worker": None}
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
                    return {"status": "ready", "worker": worker}
                if mode == "decode":
                    return {
                        "status": "ready",
                        "worker": {
                            "url": worker_url,
                            "worker_type": "decode",
                            "connection_mode": "http",
                            "runtime_type": "sglang",
                        },
                    }
                return {
                    "status": "ready",
                    "worker": {
                        "url": worker_url,
                        "worker_type": "regular",
                        "connection_mode": "http",
                        "runtime_type": "sglang",
                    },
                }
    except _ResponseTooLargeError:
        logger.warning("server_info response too large for worker %s", worker_url)
    except RemoteProtocolError as e:
        logger.debug("HTTP server_info not available for worker %s: %r", worker_url, e)
    except Exception as e:
        logger.exception("Could not fetch server_info for worker %s: %r", worker_url, e)
    return {"status": "not_ready", "worker": None}


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
    return await stub.GetServerInfo(request, timeout=_GRPC_DISCOVERY_TIMEOUT)


async def _discover_grpc_server_info(
    channel: grpc.aio.Channel,
) -> tuple[Optional[_RuntimeType], Optional[Any]]:
    # Bootstrap only: router workers list has no runtime_type yet.
    for runtime_type in _GRPC_RUNTIME_TYPES:
        try:
            response = await _get_grpc_server_info(channel, runtime_type)
        except Exception as e:
            if _is_expected_grpc_discovery_error(e):
                continue
            raise
        return runtime_type, response
    return None, None


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


async def _get_grpc_worker(
    job_model: JobModel,
    *,
    worker_url: str,
    runtime_type: Optional[_RuntimeType] = None,
) -> _WorkerPayloadResult:
    try:
        async with get_service_replica_grpc_client(job_model) as channel:
            if runtime_type is not None:
                try:
                    response = await _get_grpc_server_info(channel, runtime_type)
                except Exception as e:
                    if _is_expected_grpc_discovery_error(e):
                        logger.debug("gRPC worker %s not ready (GetServerInfo)", worker_url)
                        return {"status": "not_ready", "worker": None}
                    raise
            else:
                runtime_type, response = await _discover_grpc_server_info(channel)
                if runtime_type is None or response is None:
                    logger.debug("gRPC worker %s not ready (GetServerInfo)", worker_url)
                    return {"status": "not_ready", "worker": None}
    except Exception as e:
        logger.exception(
            "Could not fetch gRPC GetServerInfo for worker %s: %r",
            worker_url,
            e,
        )
        return {"status": "not_ready", "worker": None}

    worker = _grpc_server_info_to_worker(worker_url, runtime_type, response)
    return {"status": "ready", "worker": worker}


async def _get_worker(
    job_model: JobModel,
    *,
    http_worker_url: str,
    grpc_worker_url: str,
    connection_mode: Optional[_ConnectionMode] = None,
    runtime_type: Optional[_RuntimeType] = None,
) -> _WorkerPayloadResult:
    if connection_mode == "grpc":
        return await _get_grpc_worker(
            job_model, worker_url=grpc_worker_url, runtime_type=runtime_type
        )
    if connection_mode == "http":
        return await _get_http_worker(job_model, worker_url=http_worker_url)
    # Router workers list is empty and no connection_mode discovered.
    try:
        result = await _get_http_worker(job_model, worker_url=http_worker_url)
    except RemoteProtocolError as e:
        logger.debug(
            "HTTP server_info probe failed for %s (trying gRPC): %r",
            http_worker_url,
            e,
        )
        result: _WorkerPayloadResult = {"status": "not_ready", "worker": None}
    if result["status"] == "ready":
        return result
    return await _get_grpc_worker(job_model, worker_url=grpc_worker_url, runtime_type=runtime_type)


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
            ip = jpd.internal_ip or jpd.hostname
            if not ip:
                continue
            job_spec = get_job_spec(job)
            port = get_service_port(job_spec, config)
            http_worker_url = f"http://{ip}:{port}"
            grpc_worker_url = f"grpc://{ip}:{port}"
            result = await _get_worker(
                job,
                http_worker_url=http_worker_url,
                grpc_worker_url=grpc_worker_url,
                connection_mode=connection_mode,
                runtime_type=runtime_type,
            )
            if result["status"] == "ready" and result["worker"]:
                workers.append(result["worker"])
            elif result["status"] == "not_ready":
                logger.debug(
                    "Worker not ready http=%s grpc=%s",
                    http_worker_url,
                    grpc_worker_url,
                )
    return workers


async def sync_router_workers_for_run_model(run_model: RunModel) -> None:
    run_spec = RunSpec.__response__.parse_raw(run_model.run_spec)
    config = run_spec.configuration
    if not isinstance(config, ServiceConfiguration):
        return
    replica_groups = config.replica_groups
    router_group = next((g for g in replica_groups if g.router is not None), None)
    if router_group is None:
        return

    router_job = _get_router_job(run_model, router_group)
    if router_job is None:
        return
    try:
        async with get_service_replica_client(router_job) as client:
            current_workers = await _get_router_workers(client)
            # connection_mode can be grpc or http, runtime_type can be sglang or vllm.
            connection_mode = _get_connection_mode_from_workers(current_workers)
            runtime_type = _get_runtime_type_from_workers(current_workers)
            # Empty current_workers on first sync is expected. First syncprobes both connection_mode and
            # runtime_type. Subsequent syncs don't need to probe again because connection_mode and runtime_type
            # is already set in current_workers.
            target_workers = await _build_target_workers(
                run_model,
                run_spec,
                replica_groups,
                connection_mode=connection_mode,
                runtime_type=runtime_type,
            )
            await _update_workers_in_router_replica(
                client, target_workers, current_workers=current_workers
            )
    except SSHError as e:
        logger.warning(
            "%s: failed to sync workers with router: %r",
            fmt(router_job),
            e,
        )
