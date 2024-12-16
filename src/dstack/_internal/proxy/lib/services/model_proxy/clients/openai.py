from typing import AsyncIterator

import httpx
from fastapi import status
from pydantic import ValidationError

from dstack._internal.proxy.lib.errors import ProxyError
from dstack._internal.proxy.lib.schemas.model_proxy import (
    ChatCompletionsChunk,
    ChatCompletionsRequest,
    ChatCompletionsResponse,
)
from dstack._internal.proxy.lib.services.model_proxy.clients.base import ChatCompletionsClient


class OpenAIChatCompletions(ChatCompletionsClient):
    def __init__(self, http_client: httpx.AsyncClient, prefix: str):
        self._http = http_client
        self._prefix = prefix

    async def generate(self, request: ChatCompletionsRequest) -> ChatCompletionsResponse:
        try:
            resp = await self._http.post(
                f"{self._prefix}/chat/completions", json=request.dict(exclude_unset=True)
            )
            await self._propagate_error(resp)
        except httpx.RequestError as e:
            raise ProxyError(f"Error requesting model: {e!r}", status.HTTP_502_BAD_GATEWAY)

        try:
            return ChatCompletionsResponse.__response__.parse_raw(resp.content)
        except ValidationError as e:
            raise ProxyError(f"Invalid response from model: {e}", status.HTTP_502_BAD_GATEWAY)

    async def stream(self, request: ChatCompletionsRequest) -> AsyncIterator[ChatCompletionsChunk]:
        try:
            async with self._http.stream(
                "POST", f"{self._prefix}/chat/completions", json=request.dict(exclude_unset=True)
            ) as resp:
                await self._propagate_error(resp)

                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    yield self._parse_chunk_data(data)
        except httpx.RequestError as e:
            raise ProxyError(f"Error requesting model: {e!r}", status.HTTP_502_BAD_GATEWAY)

    @staticmethod
    def _parse_chunk_data(data: str) -> ChatCompletionsChunk:
        try:
            return ChatCompletionsChunk.__response__.parse_raw(data)
        except ValidationError as e:
            raise ProxyError(f"Invalid chunk in model stream: {e}", status.HTTP_502_BAD_GATEWAY)

    @staticmethod
    async def _propagate_error(resp: httpx.Response) -> None:
        """
        Propagates HTTP error by raising ProxyError if status is not 200.
        May also raise httpx.RequestError if there are issues reading the response.
        """
        if resp.status_code != 200:
            resp_body = await resp.aread()
            raise ProxyError(resp_body.decode(errors="replace"), code=resp.status_code)
