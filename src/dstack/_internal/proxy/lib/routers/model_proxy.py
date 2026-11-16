import asyncio
from typing import Annotated, AsyncIterator, Optional

import anyio
from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from dstack._internal.proxy.lib.cancellation import await_completion
from dstack._internal.proxy.lib.deps import (
    ProxyAuth,
    ProxyAuthContext,
    ProxyDependencyInjector,
    get_injector,
    get_proxy_repo,
    get_service_connection_pool,
)
from dstack._internal.proxy.lib.errors import ProxyError, UnexpectedProxyError
from dstack._internal.proxy.lib.repo import BaseProxyRepo
from dstack._internal.proxy.lib.schemas.model_proxy import (
    ChatCompletionsChunk,
    ChatCompletionsRequest,
    ChatCompletionsResponse,
    Model,
    ModelsResponse,
)
from dstack._internal.proxy.lib.schemas.usage import UsageKey
from dstack._internal.proxy.lib.services.model_proxy.model_proxy import get_chat_client
from dstack._internal.proxy.lib.services.service_connection import (
    ServiceConnectionPool,
    get_service_replica_client,
)
from dstack._internal.proxy.lib.services.usage import UsageAttempt

_model_auth = ProxyAuth(auto_enforce=True)
router = APIRouter(dependencies=[Depends(_model_auth)])


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
    auth: Annotated[ProxyAuthContext, Depends(_model_auth)],
    injector: Annotated[ProxyDependencyInjector, Depends(get_injector)],
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
    observer = injector.get_usage_observer()
    profile = observer.profile_for(service.id)
    attempt = None
    if profile is not None:
        if service.id is None or model.format_spec.format != "openai":
            raise ProxyError("Metering requires a registered OpenAI service", 503)
        subject = await auth.require_subject()
        attempt = observer.start_attempt(
            UsageKey(consumer_subject_id=subject.consumer_subject_id, service_id=service.id),
            profile,
        )
    transferred = False
    try:
        http_client = await get_service_replica_client(service, repo, service_conn_pool)
        client = get_chat_client(model, http_client)
        if not body.stream:
            if attempt is None:
                return await client.generate(body)
            return await client.generate(body, attempt=attempt)
        source = client.stream(body) if attempt is None else client.stream(body, attempt=attempt)
        adaptor = StreamingAdaptor(source, attempt=attempt)
        stream = await adaptor.get_stream()
        response = MeteredStreamingResponse(
            stream,
            adaptor=adaptor,
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no"},
        )
        transferred = True
        return response
    finally:
        if attempt is not None and not transferred:
            with anyio.CancelScope(shield=True):
                await attempt.finish()


class StreamingAdaptor:
    """
    Converts a stream of ChatCompletionsChunk to an SSE stream.
    Also pre-fetches the first chunk **before** starting streaming to downstream,
    so that upstream request errors can propagate to the downstream client.
    """

    def __init__(
        self, stream: AsyncIterator[ChatCompletionsChunk], attempt: UsageAttempt | None = None
    ) -> None:
        self._stream = stream
        self._attempt = attempt
        self._close_task: asyncio.Task | None = None

    async def get_stream(self) -> AsyncIterator[bytes]:
        try:
            first_chunk = await self._stream.__anext__()
        except StopAsyncIteration:
            first_chunk = None
        return self._adaptor(first_chunk)

    async def _adaptor(self, first_chunk: Optional[ChatCompletionsChunk]) -> AsyncIterator[bytes]:
        try:
            if first_chunk is not None:
                yield self._encode_chunk(first_chunk)
                try:
                    async for chunk in self._stream:
                        yield self._encode_chunk(chunk)
                except ProxyError as exc:
                    yield f": {exc.detail!r}\n\n".encode()
                    return
            yield b"data: [DONE]\n\n"
        finally:
            await self.aclose()

    async def aclose(self) -> None:
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close())
        await await_completion(self._close_task)

    async def _close(self) -> None:
        try:
            close = getattr(self._stream, "aclose", None)
            if close is not None:
                await close()
        finally:
            if self._attempt is not None:
                await self._attempt.finish()

    @staticmethod
    def _encode_chunk(chunk: ChatCompletionsChunk) -> bytes:
        encoded = chunk.model_dump_json(exclude={"usage"} if chunk.usage is None else None)
        return f"data:{encoded}\n\n".encode()


class MeteredStreamingResponse(StreamingResponse):
    def __init__(self, content, *, adaptor: StreamingAdaptor, **kwargs):
        super().__init__(content, **kwargs)
        self._adaptor = adaptor

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self._adaptor.aclose()
