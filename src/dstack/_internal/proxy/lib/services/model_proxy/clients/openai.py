import json
from typing import AsyncIterator

import httpx
from fastapi import status
from pydantic import ValidationError

from dstack._internal.core.models.common import validate_extra_ignore, validate_json_extra_ignore
from dstack._internal.proxy.lib.errors import ProxyError
from dstack._internal.proxy.lib.schemas.model_proxy import (
    ChatCompletionsChunk,
    ChatCompletionsRequest,
    ChatCompletionsResponse,
)
from dstack._internal.proxy.lib.services.model_proxy.clients.base import ChatCompletionsClient
from dstack._internal.proxy.lib.services.model_proxy.sse import SSEDecoder
from dstack._internal.proxy.lib.services.model_proxy.stream_usage import StreamUsage
from dstack._internal.proxy.lib.services.usage import MAX_JSON_RESPONSE_BYTES, UsageAttempt


class OpenAIChatCompletions(ChatCompletionsClient):
    def __init__(self, http_client: httpx.AsyncClient, prefix: str):
        self._http = http_client
        self._prefix = prefix

    async def generate(
        self, request: ChatCompletionsRequest, *, attempt: UsageAttempt | None = None
    ) -> ChatCompletionsResponse:
        try:
            if attempt is not None:
                attempt.mark_dispatched()
            async with self._http.stream(
                "POST",
                f"{self._prefix}/chat/completions",
                json=request.model_dump(exclude_unset=True),
            ) as resp:
                await self._propagate_error(resp)
                raw = await self._read_body(resp)
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("Expected a response object")
            response = validate_json_extra_ignore(ChatCompletionsResponse, raw)
            if attempt is not None:
                attempt.observe_usage(data.get("usage"))
                attempt.mark_upstream_done()
            return response
        except httpx.RequestError as exc:
            raise ProxyError(
                f"Error requesting model: {exc!r}", status.HTTP_502_BAD_GATEWAY
            ) from exc
        except (ValueError, ValidationError) as exc:
            raise ProxyError("Invalid response from model", status.HTTP_502_BAD_GATEWAY) from exc

    async def stream(
        self, request: ChatCompletionsRequest, *, attempt: UsageAttempt | None = None
    ) -> AsyncIterator[ChatCompletionsChunk]:
        payload = request.model_dump(exclude_unset=True)
        include_usage = request.stream_options is not None and request.stream_options.include_usage
        stream_usage = StreamUsage(attempt, request.n) if attempt is not None else None
        if stream_usage is not None:
            stream_options = {**(payload.get("stream_options") or {}), "include_usage": True}
            if stream_usage.request_progress:
                stream_options["continuous_usage_stats"] = True
            payload["stream_options"] = stream_options
        try:
            if attempt is not None:
                attempt.mark_dispatched()
            async with self._http.stream(
                "POST", f"{self._prefix}/chat/completions", json=payload
            ) as resp:
                await self._propagate_error(resp)
                decoder = SSEDecoder()
                async for fragment in resp.aiter_bytes():
                    for data in decoder.feed(fragment):
                        if data.strip() == "[DONE]":
                            if attempt is not None:
                                attempt.mark_upstream_done()
                            if stream_usage is not None:
                                final = stream_usage.complete()
                                if include_usage and final is not None:
                                    yield final
                            return
                        if stream_usage is None:
                            yield self._parse_chunk_data(data)
                            continue
                        raw = json.loads(data)
                        if not isinstance(raw, dict):
                            raise ValueError("Expected an SSE response object")
                        # Usage validation must not discard a choice containing text.
                        usage = raw.pop("usage", None)
                        chunk = validate_extra_ignore(ChatCompletionsChunk, raw)
                        final = stream_usage.observe(chunk, usage)
                        if chunk.choices or usage is None:
                            yield chunk
                        elif include_usage and final is not None:
                            yield final
                decoder.finish()
                raise ProxyError(
                    "Model stream ended before upstream [DONE]", status.HTTP_502_BAD_GATEWAY
                )
        except httpx.RequestError as exc:
            raise ProxyError(
                f"Error requesting model: {exc!r}", status.HTTP_502_BAD_GATEWAY
            ) from exc
        except (ValueError, ValidationError) as exc:
            raise ProxyError("Invalid event in model stream", status.HTTP_502_BAD_GATEWAY) from exc

    @staticmethod
    def _parse_chunk_data(data: str) -> ChatCompletionsChunk:
        try:
            return validate_json_extra_ignore(ChatCompletionsChunk, data)
        except ValidationError as exc:
            raise ProxyError("Invalid chunk in model stream", status.HTTP_502_BAD_GATEWAY) from exc

    @staticmethod
    async def _read_body(resp: httpx.Response) -> bytes:
        body = bytearray()
        async for fragment in resp.aiter_bytes():
            if len(body) + len(fragment) > MAX_JSON_RESPONSE_BYTES:
                raise ProxyError("Model response exceeds size limit", status.HTTP_502_BAD_GATEWAY)
            body.extend(fragment)
        return bytes(body)

    @classmethod
    async def _propagate_error(cls, resp: httpx.Response) -> None:
        if resp.status_code != 200:
            body = await cls._read_body(resp)
            raise ProxyError(body.decode(errors="replace"), code=resp.status_code)
