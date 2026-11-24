"""
Chat completions for models with the `openai` format. Requests and responses pass through
unchanged, and the tokens that the model reports in `usage` are metered.
"""

import asyncio
from typing import Annotated, Any, AsyncIterator, Coroutine, Optional, TypeVar

import httpx2 as httpx
from fastapi import Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.types import Receive, Scope, Send

from dstack._internal.proxy.lib.auth import ProxyCaller
from dstack._internal.proxy.lib.errors import ProxyError
from dstack._internal.proxy.lib.metering import BaseProxyMeter
from dstack._internal.proxy.lib.models import Service
from dstack._internal.proxy.lib.repo import BaseProxyRepo
from dstack._internal.proxy.lib.schemas.model_proxy import (
    ChatCompletionsPassthroughRequest,
    ChatCompletionsStreamOptions,
)
from dstack._internal.proxy.lib.services.service_connection import (
    ServiceConnectionPool,
    get_service_replica_client,
)
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)
T = TypeVar("T")
ModelT = TypeVar("ModelT", bound=BaseModel)

_MAX_TOKEN_COUNT = 2**31
"""Counts above this are not real. `usage` that has them is ignored."""
_TokenCount = Annotated[Optional[int], Field(ge=0, le=_MAX_TOKEN_COUNT)]


async def forward_chat_completions(
    request: Request,
    body: ChatCompletionsPassthroughRequest,
    prefix: str,
    service: Service,
    export_id: Optional[str],
    caller: ProxyCaller,
    repo: BaseProxyRepo,
    service_conn_pool: ServiceConnectionPool,
    meter: BaseProxyMeter,
) -> Response:
    """
    Forwards the request to the service and returns the service's response, whatever its status.
    Meters the tokens of the response as they are counted. If the client disconnects,
    closes the connection to the service, so that the model stops generating.

    `service` must have at least one replica. `export_id` is the export that the request
    comes through, `None` for a request to the project's own model.
    """
    stream_options = body.stream_options or ChatCompletionsStreamOptions()
    if body.stream:
        # Ask for token counts on every chunk, so that a stream the client stops is metered too.
        body = body.model_copy(
            update={
                "stream_options": stream_options.model_copy(
                    update={"include_usage": True, "continuous_usage_stats": True}
                )
            }
        )
    request_meter = _RequestMeter(meter, caller, service, export_id)
    client = await get_service_replica_client(service, repo, service_conn_pool)
    upstream_request = client.build_request(
        "POST", f"{prefix}/chat/completions", json=body.model_dump(exclude_unset=True)
    )
    try:
        upstream_response = await _run_until_disconnect(
            request, client.send(upstream_request, stream=True)
        )
    except httpx.RequestError as e:
        raise ProxyError(f"Error requesting model: {e!r}", status.HTTP_502_BAD_GATEWAY)
    # A service that ignores `stream` responds with JSON, which is not a stream
    content_type = upstream_response.headers.get("content-type", "")
    is_stream = body.stream and not content_type.startswith("application/json")
    if is_stream and upstream_response.status_code == status.HTTP_200_OK:
        return _UpstreamStreamingResponse(
            _stream(upstream_response, stream_options, request_meter),
            upstream_response=upstream_response,
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no"},
        )
    try:
        content = await _run_until_disconnect(request, upstream_response.aread())
    except httpx.RequestError as e:
        raise ProxyError(f"Error requesting model: {e!r}", status.HTTP_502_BAD_GATEWAY)
    finally:
        await upstream_response.aclose()
    if upstream_response.status_code == status.HTTP_200_OK:
        request_meter.update(_parse(_Completion, content).usage)
        request_meter.log_if_no_counts()
    response = Response(
        content=content,
        status_code=upstream_response.status_code,
        media_type=upstream_response.headers.get("content-type"),
    )
    if "retry-after" in upstream_response.headers:
        response.headers["Retry-After"] = upstream_response.headers["retry-after"]
    return response


class _UpstreamStreamingResponse(StreamingResponse):
    """
    Closes the response of the service when the stream is over,
    including when the client disconnects before the stream starts.
    """

    def __init__(self, *args: Any, upstream_response: httpx.Response, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._upstream_response = upstream_response

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self._upstream_response.aclose()


class _PromptTokensDetails(BaseModel):
    model_config = ConfigDict(extra="allow")

    cached_tokens: _TokenCount = None


class _Usage(BaseModel):
    """Token counts of a request so far. `prompt_tokens` includes `cached_tokens`."""

    model_config = ConfigDict(extra="allow")

    prompt_tokens: _TokenCount = None
    completion_tokens: _TokenCount = None
    prompt_tokens_details: Optional[_PromptTokensDetails] = None


class _Completion(BaseModel):
    usage: Optional[_Usage] = None


class _Chunk(BaseModel):
    model_config = ConfigDict(extra="allow")

    choices: Optional[list[Any]] = None
    usage: Optional[_Usage] = None


class _Choice(BaseModel):
    index: int = 0
    finish_reason: Optional[str] = None


class _StreamError(BaseModel):
    message: str
    code: int


class _StreamErrorEvent(BaseModel):
    """
    Reports an error to a client that already got `200` and a part of the stream.
    OpenAI SDKs raise an error on an event with `error`.
    """

    error: _StreamError


class _RequestMeter:
    """
    Meters one request. The counts in `usage` are totals for the request so far,
    so each update adds only what is new since the previous one.
    """

    def __init__(
        self,
        meter: BaseProxyMeter,
        caller: ProxyCaller,
        service: Service,
        export_id: Optional[str],
    ) -> None:
        self._meter = meter
        self._caller = caller
        self._service = service
        self._export_id = export_id
        self._input_tokens = 0
        self._cached_input_tokens = 0
        self._output_tokens = 0

    def update(self, usage: Optional[_Usage]) -> None:
        if usage is None:
            return
        details = usage.prompt_tokens_details
        input_tokens = max((usage.prompt_tokens or 0) - self._input_tokens, 0)
        cached_input_tokens = max(
            ((details.cached_tokens or 0) if details is not None else 0)
            - self._cached_input_tokens,
            0,
        )
        output_tokens = max((usage.completion_tokens or 0) - self._output_tokens, 0)
        if not (input_tokens or cached_input_tokens or output_tokens):
            return
        self._input_tokens += input_tokens
        self._cached_input_tokens += cached_input_tokens
        self._output_tokens += output_tokens
        self._meter.add(
            self._caller,
            self._service,
            self._export_id,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
        )

    def log_if_no_counts(self) -> None:
        if not (self._input_tokens or self._output_tokens):
            logger.debug("Service %s returned no token counts", self._service.fmt())


async def _stream(
    upstream_response: httpx.Response,
    stream_options: ChatCompletionsStreamOptions,
    request_meter: _RequestMeter,
) -> AsyncIterator[bytes]:
    """
    Yields the stream as the service sends it, without the `usage` that the client
    did not ask for in `stream_options`. If the service's stream breaks or ends before
    the response is complete, the stream ends with an error event, so that the client
    can tell it from a complete response.
    """
    keep_last_usage = stream_options.include_usage is True
    keep_all_usage = keep_last_usage and stream_options.continuous_usage_stats is True
    is_event_dropped = False
    is_done = False
    # Indexes of the choices by whether the service has sent their `finish_reason`
    finished_choices: set[int] = set()
    unfinished_choices: set[int] = set()
    # The last chunk with choices whose `usage` was removed, until the client gets
    # the last `usage` that it asked for
    last_chunk_with_usage: Optional[_Chunk] = None

    def process(line: str) -> Optional[str]:
        nonlocal is_event_dropped, last_chunk_with_usage, is_done
        if is_event_dropped and not line:
            # The blank line that ended the dropped event
            is_event_dropped = False
            return None
        if not line.startswith("data:"):
            return line
        data = line.removeprefix("data:")
        if data.strip() == "[DONE]":
            is_done = True
            if last_chunk_with_usage is None:
                return line
            # Some services, e.g. Dynamo, report the last `usage` in the last chunk
            # with choices and send no chunk only for `usage`. The client still gets one.
            usage_chunk = last_chunk_with_usage.model_copy(update={"choices": []})
            last_chunk_with_usage = None
            return "data: " + usage_chunk.model_dump_json(exclude_unset=True) + "\n\n" + line
        chunk = _parse(_Chunk, data)
        request_meter.update(chunk.usage)
        for choice in _parse_choices(chunk):
            if choice.finish_reason is not None:
                finished_choices.add(choice.index)
                unfinished_choices.discard(choice.index)
            elif choice.index not in finished_choices:
                unfinished_choices.add(choice.index)
        if keep_all_usage or "usage" not in chunk.model_fields_set:
            return line
        # A chunk with no choices and `usage: null` does not report `usage`,
        # e.g. SGLang sends its `sglext` in such a chunk
        if chunk.choices or chunk.usage is None:
            if keep_last_usage and chunk.usage is not None:
                last_chunk_with_usage = chunk
            return "data: " + chunk.model_dump_json(exclude={"usage"}, exclude_unset=True)
        # The last chunk, which the service sends only to report `usage`
        if keep_last_usage:
            last_chunk_with_usage = None
            return line
        is_event_dropped = True
        return None

    def is_complete() -> bool:
        # Not every service ends its stream with `[DONE]`. Without it, the response
        # is complete if every choice has got its `finish_reason`.
        return is_done or (bool(finished_choices) and not unfinished_choices)

    rest = ""
    try:
        async for text in upstream_response.aiter_text():
            *lines, rest = (rest + text).split("\n")
            processed = [process(line.removesuffix("\r")) for line in lines]
            if data := "".join(line + "\n" for line in processed if line is not None):
                yield data.encode()
        line = process(rest)
        request_meter.log_if_no_counts()
        if is_complete():
            if line:
                yield line.encode()
        else:
            # `rest` is not sent: it is a line that the service did not finish
            yield _get_error_event("the response ended before it was complete")
    except httpx.RequestError as e:
        if not is_complete():
            yield _get_error_event(repr(e))


def _parse_choices(chunk: _Chunk) -> list[_Choice]:
    """Returns the choices of `chunk` that are what dstack-proxy expects from the service."""
    choices = []
    for choice in chunk.choices or []:
        try:
            choices.append(_Choice.model_validate(choice))
        except ValidationError:
            pass
    return choices


def _get_error_event(detail: str) -> bytes:
    event = _StreamErrorEvent(
        error=_StreamError(
            message=f"Error requesting model: {detail}", code=status.HTTP_502_BAD_GATEWAY
        )
    )
    # The blank line first ends the event that the service may have left unfinished
    return f"\ndata: {event.model_dump_json()}\n\n".encode()


def _parse(model: type[ModelT], data: bytes | str) -> ModelT:
    """Returns an empty `model` if `data` isn't what dstack-proxy expects from the service."""
    try:
        return model.model_validate_json(data)
    except ValidationError:
        return model()


async def _run_until_disconnect(request: Request, coro: Coroutine[Any, Any, T]) -> T:
    """
    Awaits `coro`. If the client disconnects first, cancels `coro` and raises `ProxyError`.
    The tokens of the response are then not metered, since nobody receives it.
    """
    task = asyncio.ensure_future(coro)
    disconnect_watcher = asyncio.ensure_future(_wait_for_disconnect(request))
    try:
        await asyncio.wait([task, disconnect_watcher], return_when=asyncio.FIRST_COMPLETED)
    finally:
        disconnect_watcher.cancel()
        if not task.done():
            task.cancel()
            # The cancelled request releases its connection before the handler goes on.
            await asyncio.wait([task])
    if task.cancelled():
        raise ProxyError("Client disconnected")
    return task.result()


async def _wait_for_disconnect(request: Request) -> None:
    while (await request.receive())["type"] != "http.disconnect":
        pass
