"""Reconcile SGLang router /workers with dstack's registered worker replicas (async, SSH-tunneled)."""

import json
from typing import Any, Dict, List, Literal, Optional, TypedDict
from urllib.parse import urlsplit, urlunsplit

from httpx import AsyncClient, Response
from typing_extensions import NotRequired

from dstack._internal.core.errors import SSHError
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.runs import JobStatus, RunSpec, get_service_port
from dstack._internal.server.models import JobModel, RunModel
from dstack._internal.server.services.jobs import get_job_provisioning_data, get_job_spec
from dstack._internal.server.services.jobs.job_replica_http_client import (
    get_service_replica_client,
)
from dstack._internal.server.services.logging import fmt
from dstack._internal.utils.logging import get_logger

from .replicas import job_belongs_to_group
from .service_router_worker_sync import run_spec_has_router_replica_group

logger = get_logger(__name__)

_ROUTER_HTTP = "http://dstack"
_ROUTER_HTTP_TIMEOUT = 10.0
_MAX_SERVER_INFO_RESPONSE_BYTES = 256 * 1024
_MAX_WORKERS_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_WORKERS_COMMAND_ACK_BYTES = 64 * 1024
_MAX_WORKERS_LIST_ITEMS = 8192


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


class _WorkerPayloadResult(TypedDict):
    status: Literal["ready", "not_ready"]
    payload: Optional[Dict[str, Any]]


class _TargetWorker(TypedDict):
    url: str
    worker_type: str
    bootstrap_port: NotRequired[Optional[int]]


def run_model_has_router_replica_group(run_model: RunModel) -> bool:
    run_spec = RunSpec.__response__.parse_raw(run_model.run_spec)
    return run_spec_has_router_replica_group(run_spec)


def _get_router_job(run_model: RunModel, router_group) -> Optional[JobModel]:
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
    except Exception:
        logger.exception("Error getting router /workers")
    return []


async def _add_worker_to_router(
    client: AsyncClient,
    url: str,
    worker_type: str = "regular",
    bootstrap_port: Optional[int] = None,
) -> bool:
    try:
        payload: dict = {"url": url, "worker_type": worker_type}
        if bootstrap_port is not None:
            payload["bootstrap_port"] = bootstrap_port
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
) -> None:
    current = await _get_router_workers(client)
    current_urls: set[str] = set()
    current_ids_by_norm_url: dict[str, str] = {}
    for w in current:
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


async def _get_worker_payload(job_model: JobModel, worker_url: str) -> _WorkerPayloadResult:
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
                    return {"status": "not_ready", "payload": None}
                mode = data.get("disaggregation_mode", "")
                if mode == "prefill":
                    bootstrap_port = data.get("disaggregation_bootstrap_port")
                    return {
                        "status": "ready",
                        "payload": {
                            "url": worker_url,
                            "worker_type": "prefill",
                            "bootstrap_port": bootstrap_port,
                        },
                    }
                if mode == "decode":
                    return {
                        "status": "ready",
                        "payload": {"url": worker_url, "worker_type": "decode"},
                    }
                return {
                    "status": "ready",
                    "payload": {"url": worker_url, "worker_type": "regular"},
                }
    except _ResponseTooLargeError:
        logger.warning("server_info response too large for worker %s", worker_url)
    except Exception as e:
        logger.exception("Could not fetch server_info for worker %s: %r", worker_url, e)
    return {"status": "not_ready", "payload": None}


async def _build_target_workers(
    run_model: RunModel,
    run_spec: RunSpec,
    replica_groups: List,
) -> List[_TargetWorker]:
    payloads: List[_TargetWorker] = []
    config = run_spec.configuration
    if not isinstance(config, ServiceConfiguration):
        return payloads

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
            worker_url = f"http://{ip}:{port}"
            result = await _get_worker_payload(job, worker_url)
            if result["status"] == "ready" and result["payload"]:
                p = result["payload"]
                entry: _TargetWorker = {
                    "url": p["url"],
                    "worker_type": p.get("worker_type", "regular"),
                }
                if p.get("bootstrap_port") is not None:
                    entry["bootstrap_port"] = p["bootstrap_port"]
                payloads.append(entry)
            elif result["status"] == "not_ready":
                logger.debug("Worker %s not ready", worker_url)
    return payloads


async def sync_router_workers_for_run_model(run_model: RunModel) -> None:
    run_spec = RunSpec.__response__.parse_raw(run_model.run_spec)
    config = run_spec.configuration
    if not isinstance(config, ServiceConfiguration):
        return
    replica_groups = config.replica_groups
    router_group = next((g for g in replica_groups if g.router is not None), None)
    if router_group is None:
        return

    target_workers = await _build_target_workers(run_model, run_spec, replica_groups)
    router_job = _get_router_job(run_model, router_group)
    if router_job is None:
        return
    try:
        async with get_service_replica_client(router_job) as client:
            await _update_workers_in_router_replica(client, target_workers)
    except SSHError as e:
        logger.warning(
            "%s: failed to sync workers with router: %r",
            fmt(router_job),
            e,
        )
