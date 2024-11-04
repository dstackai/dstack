from typing import AsyncIterator

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from typing_extensions import Annotated

from dstack._internal.proxy.deps import ProxyAuth, get_proxy_repo
from dstack._internal.proxy.errors import ProxyError, UnexpectedProxyError
from dstack._internal.proxy.repos.base import BaseProxyRepo
from dstack._internal.proxy.schemas.model_proxy import (
    ChatCompletionsChunk,
    ChatCompletionsRequest,
    ChatCompletionsResponse,
    Model,
    ModelsResponse,
)
from dstack._internal.proxy.services.model_proxy import get_chat_client
from dstack._internal.proxy.services.service_connection import get_service_replica_client

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
    http_client = await get_service_replica_client(project_name, service, repo)
    client = get_chat_client(model, http_client)
    if not body.stream:
        return await client.generate(body)
    else:
        return StreamingResponse(
            stream_chunks(client.stream(body)),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no"},
        )


async def stream_chunks(chunks: AsyncIterator[ChatCompletionsChunk]) -> AsyncIterator[bytes]:
    async for chunk in chunks:
        yield f"data:{chunk.json()}\n\n".encode()
    yield "data: [DONE]\n\n".encode()
