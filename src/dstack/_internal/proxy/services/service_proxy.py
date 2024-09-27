import random
from typing import AsyncGenerator, AsyncIterator, Optional

import fastapi
import httpx
from starlette.requests import ClientDisconnect

from dstack._internal.proxy.repos.base import BaseProxyRepo, Replica, Service
from dstack._internal.proxy.services.service_connection import service_replica_connection_pool
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def proxy(
    project_name: str,
    run_name: str,
    path: str,
    request: fastapi.Request,
    repo: BaseProxyRepo,
) -> fastapi.responses.Response:
    if "Upgrade" in request.headers:
        raise fastapi.exceptions.HTTPException(
            fastapi.status.HTTP_400_BAD_REQUEST, "Upgrading connections is not supported"
        )

    service = await repo.get_service(project_name, run_name)
    if service is None or not service.replicas:
        raise fastapi.HTTPException(
            fastapi.status.HTTP_404_NOT_FOUND,
            f"Service {project_name}/{run_name} not found",
        )
    if service.auth:
        # TODO(#1595): support auth
        raise fastapi.HTTPException(
            fastapi.status.HTTP_400_BAD_REQUEST,
            f"Service {project_name}/{run_name} requires auth, which is not yet supported",
        )

    replica = random.choice(service.replicas)
    client = await get_replica_client(project_name, service, replica, repo)

    try:
        upstream_request = await build_upstream_request(request, path, client, replica.id)
    except ClientDisconnect:
        logger.debug(
            "Downstream client disconnected before response was sent for %s %s",
            request.method,
            request.url,
        )
        raise fastapi.HTTPException(fastapi.status.HTTP_400_BAD_REQUEST, "Client disconnected")

    try:
        upstream_response = await client.send(upstream_request, stream=True)
    except httpx.RequestError as e:
        logger.debug(
            "Error requesting %s %s for replica %s: %r",
            upstream_request.method,
            upstream_request.url,
            replica.id,
            e,
        )
        if isinstance(e, httpx.TimeoutException):
            raise fastapi.HTTPException(fastapi.status.HTTP_504_GATEWAY_TIMEOUT)
        raise fastapi.HTTPException(fastapi.status.HTTP_502_BAD_GATEWAY)

    return fastapi.responses.StreamingResponse(
        stream_response(upstream_response, replica.id),
        status_code=upstream_response.status_code,
        headers=upstream_response.headers,
    )


async def get_replica_client(
    project_name: str, service: Service, replica: Replica, repo: BaseProxyRepo
) -> httpx.AsyncClient:
    connection = await service_replica_connection_pool.get(replica.id)
    if connection is None:
        project = await repo.get_project(project_name)
        if project is None:
            raise RuntimeError(f"Expected to find project {project_name} but could not")
        connection = await service_replica_connection_pool.add(project, service, replica)
    return await connection.client()


async def stream_response(
    response: httpx.Response, replica_id: str
) -> AsyncGenerator[bytes, None]:
    try:
        async for chunk in response.aiter_raw():
            yield chunk
    except httpx.RequestError as e:
        logger.debug(
            "Error streaming response %s %s for replica %s: %r",
            response.request.method,
            response.request.url,
            replica_id,
            e,
        )

    try:
        await response.aclose()
    except httpx.RequestError as e:
        logger.debug(
            "Error closing response %s %s for replica %s: %r",
            response.request.method,
            response.request.url,
            replica_id,
            e,
        )


async def build_upstream_request(
    downstream_request: fastapi.Request, path: str, client: httpx.AsyncClient, replica_id: str
) -> httpx.Request:
    url = httpx.URL(path=path, query=downstream_request.url.query.encode("utf-8"))
    request_stream = await FastAPIToHttpxRequestStreamAdaptor(
        downstream_request.stream(), replica_id
    ).get_stream()
    client.cookies.clear()  # the client is shared by all users, don't leak cookies

    # TODO(#1595): add common proxy headers
    return client.build_request(
        downstream_request.method, url, headers=downstream_request.headers, content=request_stream
    )


class FastAPIToHttpxRequestStreamAdaptor:
    """
    If a FastAPI request has no body, its stream consists of empty byte sequences (b"").
    This adaptor detects such streams and replaces them with None, otherwise httpx will
    considers them actual request bodies, which can lead to unexpected behavior.
    """

    def __init__(self, stream: AsyncIterator[bytes], replica_id: str) -> None:
        self._stream = stream
        self._replica_id = replica_id

    async def get_stream(self) -> Optional[AsyncGenerator[bytes, None]]:
        try:
            first_chunk = await self._stream.__anext__()
        except StopAsyncIteration:
            return None
        except ClientDisconnect:
            logger.debug(
                "Downstream client disconnected when requesting replica %s", self._replica_id
            )
            return None
        if first_chunk == b"":
            return None
        return self._adaptor(first_chunk)

    async def _adaptor(self, first_chunk: bytes) -> AsyncGenerator[bytes, None]:
        yield first_chunk
        try:
            async for chunk in self._stream:
                yield chunk
        except ClientDisconnect:
            logger.debug(
                "Downstream client disconnected when requesting replica %s", self._replica_id
            )
