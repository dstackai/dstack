from typing import Annotated, AsyncIterator, Optional

from fastapi import APIRouter, Depends, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from dstack._internal.proxy.lib.auth import ProxyCaller
from dstack._internal.proxy.lib.deps import (
    get_proxy_caller,
    get_proxy_meter,
    get_proxy_repo,
    get_service_connection_pool,
)
from dstack._internal.proxy.lib.errors import ProxyError, UnexpectedProxyError
from dstack._internal.proxy.lib.metering import BaseProxyMeter
from dstack._internal.proxy.lib.models import OpenAIChatModelFormat
from dstack._internal.proxy.lib.repo import BaseProxyRepo
from dstack._internal.proxy.lib.schemas.model_proxy import (
    ChatCompletionsChunk,
    ChatCompletionsPassthroughRequest,
    ChatCompletionsRequest,
    Model,
    ModelsResponse,
)
from dstack._internal.proxy.lib.services.model_proxy.model_proxy import get_chat_client
from dstack._internal.proxy.lib.services.model_proxy.passthrough import forward_chat_completions
from dstack._internal.proxy.lib.services.service_connection import (
    ServiceConnectionPool,
    get_service_replica_client,
)

router = APIRouter(dependencies=[Depends(get_proxy_caller)])


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


@router.post("/{project_name}/chat/completions")
async def post_chat_completions(
    project_name: str,
    body: ChatCompletionsPassthroughRequest,
    request: Request,
    caller: Annotated[ProxyCaller, Depends(get_proxy_caller)],
    repo: Annotated[BaseProxyRepo, Depends(get_proxy_repo)],
    service_conn_pool: Annotated[ServiceConnectionPool, Depends(get_service_connection_pool)],
    meter: Annotated[BaseProxyMeter, Depends(get_proxy_meter)],
):
    model = await repo.get_model(project_name, body.model)
    if model is None:
        raise ProxyError(
            f"Model {body.model} not found in project {project_name}", status.HTTP_404_NOT_FOUND
        )
    service = await repo.get_service(model.project_name, model.run_name)
    if service is None or not service.replicas:
        raise UnexpectedProxyError(
            f"Model {model.name} in project {project_name} references run {model.run_name}"
            " that does not exist or has no replicas"
        )
    if isinstance(model.format_spec, OpenAIChatModelFormat):
        return await forward_chat_completions(
            request=request,
            body=body,
            prefix=model.format_spec.prefix,
            service=service,
            export_id=model.export_id,
            caller=caller,
            repo=repo,
            service_conn_pool=service_conn_pool,
            meter=meter,
        )
    # Models with other formats are converted to and from typed schemas and are not metered.
    try:
        typed_body = ChatCompletionsRequest.model_validate(body.model_dump(exclude_unset=True))
    except ValidationError as e:
        raise RequestValidationError(e.errors())
    http_client = await get_service_replica_client(service, repo, service_conn_pool)
    client = get_chat_client(model, http_client)
    if not typed_body.stream:
        return await client.generate(typed_body)
    else:
        return StreamingResponse(
            await StreamingAdaptor(client.stream(typed_body)).get_stream(),
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
        return f"data:{chunk.model_dump_json()}\n\n".encode()
