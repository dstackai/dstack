from typing import Annotated, AsyncIterable, AsyncIterator, Iterable, Iterator, Union

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from dstack.gateway.openai.schemas import (
    ChatCompletionsChunk,
    ChatCompletionsRequest,
    ChatCompletionsResponse,
    ModelsResponse,
)
from dstack.gateway.openai.store import OpenAIStore, get_store

router = APIRouter()


@router.get("/{project}/models")
async def get_models(
    project: str, store: Annotated[OpenAIStore, Depends(get_store)]
) -> ModelsResponse:
    return ModelsResponse(data=await store.list_models(project))


@router.post("/{project}/chat/completions", response_model=ChatCompletionsResponse)
async def post_chat_completions(
    project: str, body: ChatCompletionsRequest, store: Annotated[OpenAIStore, Depends(get_store)]
):
    client = await store.get_chat_client(project, body.model)
    if not body.stream:
        return await client.generate(body)
    else:
        return StreamingResponse(
            stream_chunks(await client.stream(body)),
            media_type="text/event-stream",
        )


async def stream_chunks(chunks: AsyncIterator[ChatCompletionsChunk]) -> AsyncIterator[bytes]:
    async for chunk in chunks:
        yield f"data: {chunk.model_dump_json()}".encode()
    yield "data: [DONE]\n".encode()
