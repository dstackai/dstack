"""Reconcile SGLang router /workers with dstack's ready worker replicas (async, SSH-tunneled)."""

import asyncio
import json
import logging
from collections.abc import Awaitable
from contextlib import AsyncExitStack
from typing import Annotated, Any, Literal, Optional
from urllib.parse import urlsplit
from uuid import UUID

import grpc
from google.protobuf.json_format import MessageToDict
from httpx import AsyncClient, RequestError, Response
from pydantic import FailFast, Field, OnErrorOmit, TypeAdapter, ValidationError
from smg_grpc_proto import (
    sglang_scheduler_pb2,
    sglang_scheduler_pb2_grpc,
    vllm_engine_pb2,
    vllm_engine_pb2_grpc,
)

# > Because of runtime limitations, Pydantic will require using the TypedDict type from
# > typing_extensions when using Python 3.12 and lower.
from typing_extensions import NotRequired, TypedDict

from dstack._internal.core.errors import DstackError, SSHError
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.runs import JobStatus, get_service_port
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
from dstack._internal.server.services.runs import get_run_spec
from dstack._internal.server.utils.common import gather_async, gather_map_async
from dstack._internal.utils.logging import get_logger

from .replicas import job_belongs_to_group
from .service_router_worker_sync import run_spec_has_sglang_router_replica_group

logger = get_logger(__name__)


def run_model_has_sglang_router_replica_group(run_model: RunModel) -> bool:
    run_spec = get_run_spec(run_model)
    return run_spec_has_sglang_router_replica_group(run_spec)


async def sync_router_workers_for_run_model(run_model: RunModel) -> None:
    run_spec = get_run_spec(run_model)
    config = run_spec.configuration
    if not isinstance(config, ServiceConfiguration):
        return

    router_groups = [g for g in config.replica_groups if g.router is not None]
    if not router_groups:
        logger.debug("%s: no router replica group, skipping worker sync", fmt(run_model))
        return
    if len(router_groups) > 1:
        logger.warning(
            "%s: more than one router replica group, skipping worker sync", fmt(run_model)
        )
        return
    router_group = router_groups[0]
    assert router_group.name is not None, "Replica group name is set by validation"

    router_jobs = [
        j
        for j in run_model.jobs
        if job_belongs_to_group(j, router_group.name) and j.status == JobStatus.RUNNING
    ]
    if not router_jobs:
        logger.debug(
            "%s: no running router job in group %s, skipping worker sync",
            fmt(run_model),
            router_group.name,
        )
        return

    worker_jobs_with_addresses = _get_worker_jobs_with_addresses(
        jobs=run_model.jobs, configuration=config, router_group_name=router_group.name
    )
    worker_address_to_job_id_map = {address: job.id for job, address in worker_jobs_with_addresses}

    # Probing the workers may take minutes, so no router tunnel is held meanwhile. Each router
    # is read first, and connected to again only if it needs updating, which in most syncs it
    # doesn't.
    router_jobs_with_worker_id_maps: list[tuple[JobModel, dict[UUID, str]]] = []
    for router_job, current_workers in await gather_map_async(
        router_jobs, _get_router_replica_workers, max_concurrency=_MAX_REPLICA_CONCURRENCY
    ):
        if current_workers is None:
            continue
        job_id_to_current_worker_id_map: dict[UUID, str] = {}
        for current_worker in current_workers:
            job_id = _get_current_worker_job_id(current_worker)
            if job_id is not None:
                job_id_to_current_worker_id_map[job_id] = current_worker["id"]
            else:
                # For backward compatibility with workers registered before
                # _DSTACK_JOB_ID_WORKER_LABEL was introduced: look up a job by worker's URL
                # TODO: remove eventually
                address = urlsplit(current_worker["url"]).netloc
                job_id = worker_address_to_job_id_map.get(address)
                if job_id is not None:
                    job_id_to_current_worker_id_map[job_id] = current_worker["id"]
        router_jobs_with_worker_id_maps.append((router_job, job_id_to_current_worker_id_map))
    if not router_jobs_with_worker_id_maps:
        logger.debug(
            "%s: no router in group %s returned its workers, skipping worker sync",
            fmt(run_model),
            router_group.name,
        )
        return

    # A set of worker job ids registered in _all_ router jobs.
    # If at least one router is missing a worker job, we will probe that job -- we don't reuse
    # worker info reported by other routers on purpose -- to avoid propagating possibly incomplete
    # (e.g., collected by an older dstack server) or stale (e.g., a dead worker servicer inside
    # a still running job) info infinitely.
    registered_worker_job_ids = set.intersection(
        *(set(id_map.keys()) for _, id_map in router_jobs_with_worker_id_maps)
    )
    job_id_to_target_worker_map: dict[UUID, _TargetWorker] = {}
    worker_jobs_to_probe: list[JobModel] = []
    probe_coros: list[Awaitable[Optional[_TargetWorker]]] = []
    for worker_job, address in worker_jobs_with_addresses:
        if worker_job.id in registered_worker_job_ids:
            continue
        worker_jobs_to_probe.append(worker_job)
        probe_coros.append(_probe_worker_replica(worker_job, address=address))
    if probe_coros:
        for worker_job, target_worker in zip(
            worker_jobs_to_probe,
            await gather_async(probe_coros, max_concurrency=_MAX_REPLICA_CONCURRENCY),
        ):
            if target_worker is None:
                continue
            _set_target_worker_job_id(target_worker, worker_job.id)
            job_id_to_target_worker_map[worker_job.id] = target_worker

    running_worker_job_ids = {job.id for job, _ in worker_jobs_with_addresses}
    sync_coros: list[Awaitable[None]] = []
    for router_job, job_id_to_current_worker_id_map in router_jobs_with_worker_id_maps:
        to_add = [
            target_worker
            for job_id, target_worker in job_id_to_target_worker_map.items()
            if job_id not in job_id_to_current_worker_id_map
        ]
        to_remove = [
            worker_id
            for job_id, worker_id in job_id_to_current_worker_id_map.items()
            if job_id not in running_worker_job_ids
        ]
        if not to_add and not to_remove:
            logger.debug("Router %s: workers in sync", fmt(router_job))
            continue
        sync_coros.append(
            _sync_router_replica_workers(router_job, to_add=to_add, to_remove=to_remove)
        )
    if sync_coros:
        await gather_async(sync_coros, max_concurrency=_MAX_REPLICA_CONCURRENCY)


async def _get_router_replica_workers(job: JobModel) -> Optional[list["_CurrentWorker"]]:
    log_prefix = f"Router {fmt(job)}"
    try:
        async with get_service_replica_client(job) as client:
            return await _get_router_workers(client, log_prefix=log_prefix)
    except SSHError as e:
        _log_unreachable_replica(log_prefix=log_prefix, error=e)
        return None
    except Exception:
        logger.exception("%s: unexpected error when getting workers", log_prefix)
        return None


async def _sync_router_replica_workers(
    job: JobModel, *, to_add: list["_TargetWorker"], to_remove: list[str]
) -> None:
    log_prefix = f"Router {fmt(job)}"
    try:
        async with get_service_replica_client(job) as client:
            for worker in to_add:
                await _add_worker_to_router(client, log_prefix=log_prefix, worker=worker)
            for worker_id in to_remove:
                await _remove_worker_from_router(
                    client, log_prefix=log_prefix, worker_id=worker_id
                )
    except SSHError as e:
        _log_unreachable_replica(log_prefix=log_prefix, error=e)
    except Exception:
        logger.exception("%s: unexpected error when syncing workers", log_prefix)


async def _probe_worker_replica(job: JobModel, *, address: str) -> Optional["_TargetWorker"]:
    log_prefix = f"Worker {fmt(job)}"
    try:
        async with AsyncExitStack() as exit_stack:
            uds_path = await exit_stack.enter_async_context(get_service_replica_tunnel(job))
            http_client = await exit_stack.enter_async_context(
                get_service_replica_http_client_over_uds(uds_path)
            )
            grpc_channel = await exit_stack.enter_async_context(
                get_service_replica_grpc_channel_over_uds(uds_path)
            )
            tasks = [
                asyncio.create_task(
                    _probe_http_worker(http_client, log_prefix=log_prefix, address=address)
                ),
                asyncio.create_task(
                    _probe_sglang_grpc_worker(grpc_channel, log_prefix=log_prefix, address=address)
                ),
                asyncio.create_task(
                    _probe_vllm_grpc_worker(grpc_channel, log_prefix=log_prefix, address=address)
                ),
            ]
            try:
                for future in asyncio.as_completed(tasks):
                    try:
                        worker = await future
                    except Exception:
                        # Don't let one probe failure prevent other probes from succeeding
                        logger.exception("%s: probe failed unexpectedly", log_prefix)
                        continue
                    if worker is not None:
                        logger.debug("%s: probe succeeded: %s", log_prefix, worker)
                        return worker
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            logger.debug("%s: all probes failed", log_prefix)
    except SSHError as e:
        _log_unreachable_replica(log_prefix=log_prefix, error=e)
        return None
    except Exception:
        logger.exception("%s: unexpected error when probing", log_prefix)
        return None


def _log_unreachable_replica(log_prefix: str, error: SSHError) -> None:
    # Warning is the right level: a job only reaches `RUNNING` after the server has talked to
    # its runner over SSH, so an unreachable replica is always a regression, never a replica
    # that has not started yet.
    logger.warning("%s: failed to connect: %r", log_prefix, error)


def _get_worker_jobs_with_addresses(
    jobs: list[JobModel], configuration: ServiceConfiguration, router_group_name: str
) -> list[tuple[JobModel, str]]:
    """
    Returns a list of running worker jobs with their addresses.

    Address format is "{internal_ip or hostname}:{port}", no protocol component.

    Returns:
        A list of (JobModel, address) pairs.
    """
    worker_jobs_with_addresses: list[tuple[JobModel, str]] = []
    for job in jobs:
        job_spec = get_job_spec(job)
        if job_spec.replica_group == router_group_name:
            continue

        if job.status != JobStatus.RUNNING:
            logger.debug("%s: not running, skipping", fmt(job))
            continue

        jpd = get_job_provisioning_data(job)
        if jpd is None:
            logger.debug("%s: no job provisioning data, skipping", fmt(job))
            continue

        hostname = jpd.internal_ip
        if not hostname:
            if jpd.hostname:
                hostname = jpd.hostname
                logger.debug("%s: internal_ip is not set, using hostname as a fallback", fmt(job))
            else:
                logger.debug("%s: neither internal_ip nor hostname is set, skipping", fmt(job))
                continue

        port = get_service_port(job_spec, configuration)
        address = f"{hostname}:{port}"
        worker_jobs_with_addresses.append((job, address))

    return worker_jobs_with_addresses


def _get_current_worker_job_id(worker: "_CurrentWorker") -> Optional[UUID]:
    labels = worker.get("labels")
    if not labels:
        return None
    job_id = labels.get(_WORKER_LABEL_DSTACK_JOB_ID)
    if not job_id:
        return None
    try:
        return UUID(job_id)
    except ValueError as e:
        logger.warning("Unparsable dstack job id worker label: %r: %s", job_id, e)
        return None


def _set_target_worker_job_id(worker: "_TargetWorker", job_id: UUID) -> None:
    labels = worker.setdefault("labels", {})
    labels[_WORKER_LABEL_DSTACK_JOB_ID] = str(job_id)


_DEFAULT_HTTP_TIMEOUT = 10.0
_MAX_LOGGED_RESPONSE_BYTES = 1024
_MAX_REPLICA_CONCURRENCY = 8

# Requests are made over a UDS tunnel to the replica, so the authority is a placeholder
# for debugging purposes only
_ROUTER_BASE_URL = "http://router"
_ROUTER_MAX_WORKERS_RESPONSE_BYTES = 2 * 1024 * 1024
_ROUTER_MAX_WORKERS_COMMAND_ACK_BYTES = 64 * 1024
_ROUTER_MAX_WORKERS_LIST_ITEMS = 8192

_WORKER_BASE_URL = "http://worker"
_WORKER_PROBE_TIMEOUT = 30.0
_WORKER_MAX_SERVER_INFO_RESPONSE_BYTES = 256 * 1024
_WORKER_LABEL_DSTACK_JOB_ID = "dstack.ai/job-id"


# https://github.com/smg-project/smg/blob/3be823a700fabaff3add8a390cf78f163479d686/crates/protocols/src/worker.rs#L903
class _CurrentWorker(TypedDict):
    id: str
    url: str
    labels: NotRequired[dict[str, str]]


class _WorkersStats(TypedDict):
    regular_count: NotRequired[OnErrorOmit[int]]
    prefill_count: NotRequired[OnErrorOmit[int]]
    decode_count: NotRequired[OnErrorOmit[int]]


class _WorkerListResponse(TypedDict):
    workers: Annotated[
        list[_CurrentWorker], Field(max_length=_ROUTER_MAX_WORKERS_LIST_ITEMS), FailFast()
    ]
    stats: NotRequired[_WorkersStats]


class _WorkerErrorResponse(TypedDict):
    error: str
    code: str


class _CreateDeleteWorkerResponse(TypedDict):
    status: str
    worker_id: str


_worker_list_response_ta = TypeAdapter(_WorkerListResponse)
_worker_error_response_ta = TypeAdapter(_WorkerErrorResponse)
_create_delete_worker_response_ta = TypeAdapter(_CreateDeleteWorkerResponse)


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
    labels: NotRequired[dict[str, str]]


# https://github.com/smg-project/smg/blob/3be823a700fabaff3add8a390cf78f163479d686/crates/protocols/src/worker.rs#L29
# Only types we support are included
_WorkerType = Literal["regular", "prefill", "decode"]

# https://github.com/smg-project/smg/blob/3be823a700fabaff3add8a390cf78f163479d686/crates/protocols/src/worker.rs#L76
# Only modes we support are included
_ConnectionMode = Literal["http", "grpc"]

# https://github.com/smg-project/smg/blob/3be823a700fabaff3add8a390cf78f163479d686/crates/protocols/src/worker.rs#L227
# Only types we support are included
_RuntimeType = Literal["sglang", "vllm"]


class _ResponseTooLargeError(DstackError):
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
    json_body: Optional[dict] = None,
    timeout: float = _DEFAULT_HTTP_TIMEOUT,
) -> tuple[int, bytes]:
    kwargs: dict[str, Any] = {"timeout": timeout}
    if json_body is not None:
        kwargs["json"] = json_body
    async with client.stream(method, url, **kwargs) as resp:
        cl = resp.headers.get("content-length")
        if cl is not None:
            try:
                if int(cl) > max_response_bytes:
                    raise _ResponseTooLargeError()
            except ValueError:
                pass
        body = await _stream_response_body_bytes(resp, max_response_bytes)
        return resp.status_code, body


def _fmt_response_body(body: bytes) -> str:
    if len(body) <= _MAX_LOGGED_RESPONSE_BYTES:
        return repr(body)
    return f"{body[:_MAX_LOGGED_RESPONSE_BYTES]!r}... ({len(body)} bytes total)"


async def _get_router_workers(
    client: AsyncClient, *, log_prefix: str
) -> Optional[list[_CurrentWorker]]:
    try:
        status_code, raw_response = await _request_json_limited(
            client,
            "GET",
            f"{_ROUTER_BASE_URL}/workers",
            max_response_bytes=_ROUTER_MAX_WORKERS_RESPONSE_BYTES,
        )
    except RequestError as e:
        logger.debug("%s: GET /workers: request failed: %r", log_prefix, e)
        return None
    except _ResponseTooLargeError:
        logger.warning("%s: GET /workers: response too large", log_prefix)
        return None

    if status_code != 200:
        logger.warning(
            "%s: GET /workers: unexpected status code: %d: %s",
            log_prefix,
            status_code,
            _fmt_response_body(raw_response),
        )
        return None

    try:
        response = _worker_list_response_ta.validate_json(raw_response)
    except ValidationError as e:
        logger.warning("%s: GET /workers: response validation failed: %s", log_prefix, e)
        return None

    logger.debug("%s: workers stats: %s", log_prefix, response.get("stats"))
    return response["workers"]


async def _add_worker_to_router(
    client: AsyncClient, *, log_prefix: str, worker: _TargetWorker
) -> None:
    url = worker["url"]
    try:
        status_code, raw_response = await _request_json_limited(
            client,
            "POST",
            f"{_ROUTER_BASE_URL}/workers",
            max_response_bytes=_ROUTER_MAX_WORKERS_COMMAND_ACK_BYTES,
            json_body=dict(worker),
        )
    except RequestError as e:
        logger.warning("%s: POST /workers: %s: request failed: %r", log_prefix, url, e)
        return
    except _ResponseTooLargeError:
        logger.warning("%s: POST /workers: %s: response too large", log_prefix, url)
        return

    if status_code == 202:
        try:
            response = _create_delete_worker_response_ta.validate_json(raw_response)
        except ValidationError as e:
            logger.warning(
                "%s: POST /workers: %s: accepted response validation failed: %s",
                log_prefix,
                url,
                e,
            )
            return

        if response["status"] != "accepted":
            logger.warning(
                "%s: POST /workers: %s: unexpected accepted status: %s",
                log_prefix,
                url,
                response["status"],
            )
        else:
            logger.debug(
                "%s: POST /workers: %s: accepted: %s", log_prefix, url, response["worker_id"]
            )

    elif status_code == 409:
        try:
            response = _worker_error_response_ta.validate_json(raw_response)
        except ValidationError as e:
            logger.warning(
                "%s: POST /workers: %s: conflict response validation failed: %s",
                log_prefix,
                url,
                e,
            )
            return

        if response["code"] not in ["WORKER_CREATE_IN_PROGRESS", "WORKER_ALREADY_EXISTS"]:
            logger.warning(
                "%s: POST /workers: %s: unexpected conflict code: %s",
                log_prefix,
                url,
                response["code"],
            )
        else:
            logger.debug("%s: POST /workers: %s: conflict: %s", log_prefix, url, response["code"])

    else:
        logger.warning(
            "%s: POST /workers: %s: unexpected status code: %d: %s",
            log_prefix,
            url,
            status_code,
            _fmt_response_body(raw_response),
        )


async def _remove_worker_from_router(
    client: AsyncClient, *, log_prefix: str, worker_id: str
) -> None:
    try:
        status_code, raw_response = await _request_json_limited(
            client,
            "DELETE",
            f"{_ROUTER_BASE_URL}/workers/{worker_id}",
            max_response_bytes=_ROUTER_MAX_WORKERS_COMMAND_ACK_BYTES,
        )
    except RequestError as e:
        logger.warning("%s: DELETE /workers/%s: request failed: %r", log_prefix, worker_id, e)
        return
    except _ResponseTooLargeError:
        logger.warning("%s: DELETE /workers/%s: response too large", log_prefix, worker_id)
        return

    if status_code != 202:
        logger.warning(
            "%s: DELETE /workers/%s: unexpected status code: %d: %s",
            log_prefix,
            worker_id,
            status_code,
            _fmt_response_body(raw_response),
        )
        return

    try:
        response = _create_delete_worker_response_ta.validate_json(raw_response)
    except ValidationError as e:
        logger.warning(
            "%s: DELETE /workers/%s: response validation failed: %s", log_prefix, worker_id, e
        )
        return

    if response["status"] != "accepted":
        logger.warning(
            "%s: DELETE /workers/%s: unexpected accepted status: %s",
            log_prefix,
            worker_id,
            response["status"],
        )
    else:
        logger.debug("%s: DELETE /workers/%s: accepted", log_prefix, worker_id)


async def _probe_http_worker(
    client: AsyncClient, *, log_prefix: str, address: str
) -> Optional[_TargetWorker]:
    # The request goes over the tunnel, `worker_url` is the address the router itself dials.
    worker_url = f"http://{address}"
    logger.debug("%s: %s: probing", log_prefix, worker_url)

    try:
        status_code, raw_response = await _request_json_limited(
            client,
            "GET",
            f"{_WORKER_BASE_URL}/server_info",
            max_response_bytes=_WORKER_MAX_SERVER_INFO_RESPONSE_BYTES,
            timeout=_WORKER_PROBE_TIMEOUT,
        )
    except RequestError as e:
        logger.debug("%s: %s: GET /server_info: request failed: %r", log_prefix, worker_url, e)
        return None
    except _ResponseTooLargeError:
        logger.warning("%s: %s: GET /server_info: response too large", log_prefix, worker_url)
        return None

    if status_code != 200:
        logger.warning(
            "%s: %s: GET /server_info: unexpected status code: %s",
            log_prefix,
            worker_url,
            status_code,
        )
        return None

    # ValueError, not JSONDecodeError: a body that is not valid UTF-8 raises UnicodeDecodeError
    try:
        data = json.loads(raw_response)
    except ValueError as e:
        logger.warning(
            "%s: %s: GET /server_info: response parsing failed: %s", log_prefix, worker_url, e
        )
        return None
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


async def _probe_sglang_grpc_worker(
    channel: grpc.aio.Channel, *, log_prefix: str, address: str
) -> Optional[_TargetWorker]:
    runtime_type: _RuntimeType = "sglang"
    # The RPC goes over the tunnel, `worker_url` is the address the router itself dials.
    worker_url = f"grpc://{address}"
    logger.debug("%s: %s: probing %s", log_prefix, worker_url, runtime_type)

    stub = sglang_scheduler_pb2_grpc.SglangSchedulerStub(channel)
    request = sglang_scheduler_pb2.GetServerInfoRequest()
    response: sglang_scheduler_pb2.GetServerInfoResponse
    try:
        response = await stub.GetServerInfo(request, timeout=_WORKER_PROBE_TIMEOUT)
    except grpc.aio.AioRpcError as e:
        _log_failed_grpc_worker_probe(
            log_prefix=log_prefix, worker_url=worker_url, runtime_type=runtime_type, error=e
        )
        return None

    server_args = MessageToDict(response.server_args, preserving_proto_field_name=True)
    worker_type: _WorkerType
    match disaggregation_mode := server_args.get("disaggregation_mode"):
        case "prefill" | "decode":
            worker_type = disaggregation_mode
        case _:
            worker_type = "regular"
    worker: _TargetWorker = {
        "url": worker_url,
        "worker_type": worker_type,
        "connection_mode": "grpc",
        "runtime_type": runtime_type,
    }
    if worker_type == "prefill":
        bootstrap_port = server_args.get("disaggregation_bootstrap_port")
        if bootstrap_port is not None:
            worker["bootstrap_port"] = int(bootstrap_port)
    return worker


async def _probe_vllm_grpc_worker(
    channel: grpc.aio.Channel, *, log_prefix: str, address: str
) -> Optional[_TargetWorker]:
    runtime_type: _RuntimeType = "vllm"
    # The RPC goes over the tunnel, `worker_url` is the address the router itself dials.
    worker_url = f"grpc://{address}"
    logger.debug("%s: %s: probing %s", log_prefix, worker_url, runtime_type)

    stub = vllm_engine_pb2_grpc.VllmEngineStub(channel)
    request = vllm_engine_pb2.GetServerInfoRequest()
    response: vllm_engine_pb2.GetServerInfoResponse
    try:
        response = await stub.GetServerInfo(request, timeout=_WORKER_PROBE_TIMEOUT)
    except grpc.aio.AioRpcError as e:
        _log_failed_grpc_worker_probe(
            log_prefix=log_prefix, worker_url=worker_url, runtime_type=runtime_type, error=e
        )
        return None

    worker_type: _WorkerType
    match response.kv_role:
        case "kv_producer":
            worker_type = "prefill"
        case "kv_consumer":
            worker_type = "decode"
        case _:
            worker_type = "regular"
    worker: _TargetWorker = {
        "url": worker_url,
        "worker_type": worker_type,
        "connection_mode": "grpc",
        "runtime_type": "vllm",
    }
    if response.kv_connector:
        worker["kv_connector"] = response.kv_connector
    if response.kv_role:
        worker["kv_role"] = response.kv_role
    return worker


def _log_failed_grpc_worker_probe(
    log_prefix: str, worker_url: str, runtime_type: _RuntimeType, error: grpc.aio.AioRpcError
):
    log_level = logging.DEBUG if _is_expected_grpc_error(error) else logging.WARNING
    logger.log(
        log_level,
        "%s: %s: %s probe failed: %s: %s",
        log_prefix,
        worker_url,
        runtime_type,
        error.code(),
        error.details(),
    )


def _is_expected_grpc_error(error: grpc.aio.AioRpcError) -> bool:
    """Expected while a gRPC worker is still starting or the wrong stub is probed."""
    return error.code() in (
        grpc.StatusCode.UNAVAILABLE,
        grpc.StatusCode.DEADLINE_EXCEEDED,
        grpc.StatusCode.UNIMPLEMENTED,
        grpc.StatusCode.CANCELLED,
    )
