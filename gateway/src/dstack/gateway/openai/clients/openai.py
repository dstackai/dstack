from typing import AsyncIterator, Optional

from dstack.gateway.common import AsyncClientWrapper
from dstack.gateway.errors import GatewayError
from dstack.gateway.openai.clients import DEFAULT_TIMEOUT, ChatCompletionsClient
from dstack.gateway.openai.schemas import (
    ChatCompletionsChunk,
    ChatCompletionsRequest,
    ChatCompletionsResponse,
)


class OpenAIChatCompletions(ChatCompletionsClient):
    def __init__(self, base_url: str, host: Optional[str] = None):
        self.client = AsyncClientWrapper(
            base_url=base_url.rstrip("/"),
            headers={} if host is None else {"Host": host},
            timeout=DEFAULT_TIMEOUT,
        )

    async def generate(self, request: ChatCompletionsRequest) -> ChatCompletionsResponse:
        resp = await self.client.post(
            "/chat/completions", json=request.model_dump(exclude_unset=True)
        )
        if resp.status_code != 200:
            raise GatewayError(resp.text)
        return ChatCompletionsResponse.model_validate(resp.json())

    async def stream(self, request: ChatCompletionsRequest) -> AsyncIterator[ChatCompletionsChunk]:
        async for data in self.client.stream_sse(
            "/chat/completions", json=request.model_dump(exclude_unset=True)
        ):
            yield ChatCompletionsChunk.model_validate(data)
