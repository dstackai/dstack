from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from typing_extensions import Annotated

from dstack._internal.proxy.lib.deps import ProxyAuth, get_proxy_repo, get_service_connection_pool
from dstack._internal.proxy.lib.errors import ProxyError, UnexpectedProxyError
from dstack._internal.proxy.lib.repo import BaseProxyRepo
from dstack._internal.proxy.lib.schemas.model_proxy import (
    ChatCompletionsChunk,
    ChatCompletionsRequest,
    ChatCompletionsResponse,
    Model,
    ModelsResponse,
)
from dstack._internal.proxy.lib.services.model_proxy.model_proxy import get_chat_client
from dstack._internal.proxy.lib.services.service_connection import (
    ServiceConnectionPool,
    get_service_replica_client,
)

router = APIRouter(dependencies=[Depends(ProxyAuth(auto_enforce=True))])


@router.get("/{project_name}/models")
async def get_models(
    project_name: str, repo: Annotated[BaseProxyRepo, Depends(get_proxy_repo)]
) -> ModelsResponse:
    models = await repo.list_models(project_name)
    data = [
        Model(id=m.name, created=int(m.created_at.timestamp()), owned_by=project_name)
        for m in models
    ]
    return ModelsResponse(data=data)


@router.post("/{project_name}/chat/completions", response_model=ChatCompletionsResponse)
async def post_chat_completions(
    project_name: str,
    body: ChatCompletionsRequest,
    repo: Annotated[BaseProxyRepo, Depends(get_proxy_repo)],
    service_conn_pool: Annotated[ServiceConnectionPool, Depends(get_service_connection_pool)],
):
    model = await repo.get_model(project_name, body.model)
    if model is None:
        raise ProxyError(
            f"Model {body.model} not found in project {project_name}", status.HTTP_404_NOT_FOUND
        )
    service = await repo.get_service(project_name, model.run_name)
    if service is None or not service.replicas:
        raise UnexpectedProxyError(
            f"Model {model.name} in project {project_name} references run {model.run_name}"
            " that does not exist or has no replicas"
        )
    http_client = await get_service_replica_client(service, repo, service_conn_pool)
    client = get_chat_client(model, http_client)
    if not body.stream:
        return await client.generate(body)
    else:
        return StreamingResponse(
            await StreamingAdaptor(client.stream(body)).get_stream(),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no"},
        )


class StreamingAdaptor:
    """
    Converts a stream of ChatCompletionsChunk to an SSE stream.
    Also pre-fetches the first chunk **before** starting streaming to downstream,
    so that upstream request errors can propagate to the downstream client.
    """

    def __init__(self, stream: AsyncIterator[ChatCompletionsChunk]) -> None:
        self._stream = stream

    async def get_stream(self) -> AsyncIterator[bytes]:
        try:
            first_chunk = await self._stream.__anext__()
        except StopAsyncIteration:
            first_chunk = None
        return self._adaptor(first_chunk)

    async def _adaptor(self, first_chunk: Optional[ChatCompletionsChunk]) -> AsyncIterator[bytes]:
        if first_chunk is not None:
            yield self._encode_chunk(first_chunk)

            try:
                async for chunk in self._stream:
                    yield self._encode_chunk(chunk)
            except ProxyError as e:
                # No standard way to report errors while streaming,
                # but we'll at least send them as comments
                yield f": {e.detail!r}\n\n".encode()  # !r to avoid line breaks
                return

        yield "data: [DONE]\n\n".encode()

    @staticmethod
    def _encode_chunk(chunk: ChatCompletionsChunk) -> bytes:
        return f"data:{chunk.json()}\n\n".encode()
