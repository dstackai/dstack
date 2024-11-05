from typing import AsyncIterator

import httpx

from dstack._internal.proxy.errors import ProxyError
from dstack._internal.proxy.schemas.model_proxy import (
    ChatCompletionsChunk,
    ChatCompletionsRequest,
    ChatCompletionsResponse,
)
from dstack._internal.proxy.services.model_proxy.clients import ChatCompletionsClient


class OpenAIChatCompletions(ChatCompletionsClient):
    def __init__(self, http_client: httpx.AsyncClient, prefix: str):
        self._http = http_client
        self._prefix = prefix

    async def generate(self, request: ChatCompletionsRequest) -> ChatCompletionsResponse:
        resp = await self._http.post(
            f"{self._prefix}/chat/completions", json=request.dict(exclude_unset=True)
        )
        if resp.status_code != 200:
            raise ProxyError(resp.text)
        return ChatCompletionsResponse.__response__.parse_raw(resp.content)

    async def stream(self, request: ChatCompletionsRequest) -> AsyncIterator[ChatCompletionsChunk]:
        async with self._http.stream(
            "POST", f"{self._prefix}/chat/completions", json=request.dict(exclude_unset=True)
        ) as resp:
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if data == "[DONE]":
                    break
                yield ChatCompletionsChunk.__response__.parse_raw(data)
