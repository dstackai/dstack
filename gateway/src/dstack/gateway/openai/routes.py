from typing import Annotated, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from dstack.gateway.errors import GatewayError
from dstack.gateway.openai.schemas import (
    ChatCompletionsChunk,
    ChatCompletionsRequest,
    ChatCompletionsResponse,
    ModelsResponse,
)
from dstack.gateway.openai.store import OpenAIStore, get_store
from dstack.gateway.services.auth import AuthProvider, get_auth


async def auth_required(
    project: str,
    auth: AuthProvider = Depends(get_auth),
    token: HTTPAuthorizationCredentials = Security(HTTPBearer()),
):
    if not await auth.has_access(project, token.credentials):
        raise HTTPException(status_code=403)


router = APIRouter(dependencies=[Depends(auth_required)])


@router.get("/{project}/models")
async def get_models(
    project: str, store: Annotated[OpenAIStore, Depends(get_store)]
) -> ModelsResponse:
    return ModelsResponse(data=await store.list_models(project))


@router.post("/{project}/chat/completions", response_model=ChatCompletionsResponse)
async def post_chat_completions(
    project: str, body: ChatCompletionsRequest, store: Annotated[OpenAIStore, Depends(get_store)]
):
    try:
        client = await store.get_chat_client(project, body.model)
        if not body.stream:
            return await client.generate(body)
        else:
            return StreamingResponse(
                stream_chunks(client.stream(body)),
                media_type="text/event-stream",
                headers={"X-Accel-Buffering": "no"},
            )
    except GatewayError as e:
        raise e.http()


async def stream_chunks(chunks: AsyncIterator[ChatCompletionsChunk]) -> AsyncIterator[bytes]:
    async for chunk in chunks:
        yield f"data:{chunk.model_dump_json()}\n\n".encode()
    yield "data: [DONE]\n\n".encode()
