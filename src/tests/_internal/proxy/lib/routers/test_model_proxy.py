import asyncio
import json
import re
from datetime import datetime
from typing import Any, AsyncIterator, Callable, Generator, Optional
from unittest.mock import patch

import httpx2 as httpx
import openai
import pytest
from fastapi import FastAPI
from starlette.types import Message, Scope

from dstack._internal.proxy.gateway.models import ImportedModel
from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.lib.auth import BaseProxyAuthProvider
from dstack._internal.proxy.lib.models import (
    AnyModelFormat,
    ChatModel,
    OpenAIChatModelFormat,
    TGIChatModelFormat,
)
from dstack._internal.proxy.lib.repo import BaseProxyRepo
from dstack._internal.proxy.lib.routers.model_proxy import router
from dstack._internal.proxy.lib.schemas.model_proxy import (
    ChatCompletionsChoice,
    ChatCompletionsChunk,
    ChatCompletionsChunkChoice,
    ChatCompletionsRequest,
    ChatCompletionsResponse,
    ChatCompletionsUsage,
    ChatMessage,
)
from dstack._internal.proxy.lib.services.model_proxy.clients.base import ChatCompletionsClient
from dstack._internal.proxy.lib.testing.auth import ProxyTestAuthProvider, make_caller
from dstack._internal.proxy.lib.testing.common import (
    ProxyTestDependencyInjector,
    make_project,
    make_service,
)
from dstack._internal.proxy.lib.testing.metering import MeteredTokens, ProxyTestMeter

SAMPLE_RESPONSE = "Hello there, how may I assist you today?"


class ChatClientStub(ChatCompletionsClient):
    async def generate(self, request: ChatCompletionsRequest) -> ChatCompletionsResponse:
        return ChatCompletionsResponse(
            id="chatcmpl-123",
            choices=[
                ChatCompletionsChoice(
                    finish_reason="stop",
                    index=0,
                    message=ChatMessage(
                        role="assistant",
                        content=SAMPLE_RESPONSE,
                    ),
                )
            ],
            created=int(datetime.now().timestamp()),
            model=request.model,
            usage=ChatCompletionsUsage(
                completion_tokens=12,
                prompt_tokens=9,
                total_tokens=21,
            ),
        )

    async def stream(self, request: ChatCompletionsRequest) -> AsyncIterator[ChatCompletionsChunk]:
        for i, word in enumerate(SAMPLE_RESPONSE.split(" ")):
            if i > 0:
                word = " " + word
            yield ChatCompletionsChunk(
                id="chatcmpl-123",
                choices=[
                    ChatCompletionsChunkChoice(
                        finish_reason=None,
                        index=0,
                        delta=dict(
                            role="assistant",
                            content=word,
                        ),
                    )
                ],
                created=int(datetime.now().timestamp()),
                model=request.model,
            )


TGI_FORMAT = TGIChatModelFormat(chat_template="", eos_token="")


def make_model(
    project_name: str,
    name: str,
    run_name: str,
    created_at: datetime = datetime.fromtimestamp(0),
    format_spec: AnyModelFormat = OpenAIChatModelFormat(format="openai", prefix="/v1"),
) -> ChatModel:
    return ChatModel(
        project_name=project_name,
        name=name,
        created_at=created_at,
        run_name=run_name,
        format_spec=format_spec,
    )


def make_app(
    repo: BaseProxyRepo, auth: BaseProxyAuthProvider, meter: Optional[ProxyTestMeter] = None
) -> FastAPI:
    app = FastAPI()
    app.state.proxy_dependency_injector = ProxyTestDependencyInjector(
        repo=repo, auth=auth, meter=meter
    )
    app.include_router(router, prefix="/proxy/models")
    return app


def make_http_client(
    repo: BaseProxyRepo, auth: BaseProxyAuthProvider, meter: Optional[ProxyTestMeter] = None
) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=make_app(repo, auth, meter)))


def make_openai_client(
    repo: BaseProxyRepo,
    auth: BaseProxyAuthProvider,
    project_name: str,
    auth_token: str = "token",
) -> openai.AsyncOpenAI:
    http_client = make_http_client(repo, auth)
    return openai.AsyncOpenAI(
        api_key=auth_token,
        base_url=f"http://test-host/proxy/models/{project_name}",
        http_client=http_client,
    )


@pytest.fixture
def mock_chat_client() -> Generator[None, None, None]:
    with (
        patch(
            "dstack._internal.proxy.lib.services.service_connection.ServiceConnectionPool.get_or_add"
        ),
        patch("dstack._internal.proxy.lib.routers.model_proxy.get_chat_client") as get_client_mock,
    ):
        get_client_mock.return_value = ChatClientStub()
        yield


@pytest.mark.asyncio
async def test_list_models() -> None:
    auth = ProxyTestAuthProvider({"test-proj": {"token"}})
    repo = GatewayProxyRepo()
    await repo.set_project(make_project("test-proj"))
    await repo.set_service(make_service("test-proj", "test-service-1"))
    await repo.set_service(make_service("test-proj", "test-service-2"))
    await repo.set_model(
        make_model(
            "test-proj", "test-model-1", "test-service-1", created_at=datetime.fromtimestamp(123)
        ),
    )
    await repo.set_model(
        make_model(
            "test-proj", "test-model-2", "test-service-2", created_at=datetime.fromtimestamp(321)
        ),
    )

    client = make_openai_client(repo, auth, "test-proj", auth_token="token")
    models = [model async for model in client.models.list()]

    assert models[0].id == "test-model-1"
    assert models[0].created == 123
    assert models[0].owned_by == "test-proj"
    assert models[1].id == "test-model-2"
    assert models[1].created == 321
    assert models[1].owned_by == "test-proj"


@pytest.mark.asyncio
async def test_list_models_empty() -> None:
    auth = ProxyTestAuthProvider({"test-proj": {"token"}, "test-proj-empty": {"token"}})
    repo = GatewayProxyRepo()
    await repo.set_project(make_project("test-proj"))
    await repo.set_project(make_project("test-proj-empty"))
    await repo.set_service(make_service("test-proj", "test-service"))
    await repo.set_model(make_model("test-proj", "test-model", "test-service"))

    client = make_openai_client(repo, auth, "test-proj-empty", auth_token="token")
    models = [model async for model in client.models.list()]
    assert not models


@pytest.mark.asyncio
async def test_chat_completions(mock_chat_client) -> None:
    auth = ProxyTestAuthProvider({"test-proj": {"token"}})
    repo = GatewayProxyRepo()
    await repo.set_project(make_project("test-proj"))
    await repo.set_service(make_service("test-proj", "test-service"))
    await repo.set_model(
        make_model("test-proj", "test-model", "test-service", format_spec=TGI_FORMAT)
    )
    client = make_openai_client(repo, auth, "test-proj", auth_token="token")
    completion = await client.chat.completions.create(
        model="test-model",
        messages=[{"role": "user", "content": "Hi"}],
    )
    assert completion.choices[0].message.content == SAMPLE_RESPONSE


@pytest.mark.asyncio
async def test_chat_completions_with_project_name_in_another_case(mock_chat_client) -> None:
    auth = ProxyTestAuthProvider({"Test-Proj": {"token"}})
    repo = GatewayProxyRepo()
    await repo.set_project(make_project("test-proj"))
    await repo.set_service(make_service("test-proj", "test-service"))
    await repo.set_model(
        make_model("test-proj", "test-model", "test-service", format_spec=TGI_FORMAT)
    )
    client = make_openai_client(repo, auth, "Test-Proj", auth_token="token")
    completion = await client.chat.completions.create(
        model="test-model",
        messages=[{"role": "user", "content": "Hi"}],
    )
    assert completion.choices[0].message.content == SAMPLE_RESPONSE


@pytest.mark.asyncio
async def test_chat_completions_stream(mock_chat_client) -> None:
    auth = ProxyTestAuthProvider({"test-proj": {"token"}})
    repo = GatewayProxyRepo()
    await repo.set_project(make_project("test-proj"))
    await repo.set_service(make_service("test-proj", "test-service"))
    await repo.set_model(
        make_model("test-proj", "test-model", "test-service", format_spec=TGI_FORMAT)
    )
    client = make_openai_client(repo, auth, "test-proj", auth_token="token")
    response = await client.chat.completions.create(
        model="test-model",
        messages=[{"role": "user", "content": "Hi"}],
        stream=True,
    )
    completion = ""
    async for chunk in response:
        content = chunk.choices[0].delta.content
        assert content is not None
        completion += content
    assert completion == SAMPLE_RESPONSE


@pytest.mark.asyncio
async def test_chat_completions_model_not_found() -> None:
    auth = ProxyTestAuthProvider({"test-proj": {"token"}})
    repo = GatewayProxyRepo()
    await repo.set_project(make_project("test-proj"))
    client = make_openai_client(repo, auth, "test-proj", auth_token="token")
    with pytest.raises(openai.NotFoundError):
        await client.chat.completions.create(
            model="unknown-model",
            messages=[{"role": "user", "content": "Hi"}],
        )


@pytest.mark.asyncio
async def test_unauthorized_openai_sdk() -> None:
    auth = ProxyTestAuthProvider({"test-proj": {"correct-token"}})
    repo = GatewayProxyRepo()
    await repo.set_project(make_project("test-proj"))
    client = make_openai_client(repo, auth, "test-proj", auth_token="invalid-token")

    with pytest.raises(openai.PermissionDeniedError):
        await client.models.list()
    with pytest.raises(openai.PermissionDeniedError):
        await client.chat.completions.create(
            model="test-model",
            messages=[{"role": "user", "content": "Hi"}],
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": "Bearer invalid-token"},
        {"Authorization": "Bearer "},
        {"Authorization": "Bearer"},
        {"Authorization": ""},
        None,
    ],
)
async def test_unauthorized_http(headers) -> None:
    auth = ProxyTestAuthProvider({"test-proj": {"correct-token"}})
    repo = GatewayProxyRepo()
    await repo.set_project(make_project("test-proj"))
    client = make_http_client(repo, auth)

    resp = await client.get("http://test-host/proxy/models/test-proj/models", headers=headers)
    assert resp.status_code == 403

    resp = await client.post(
        "http://test-host/proxy/models/test-proj/chat/completions",
        json={"model": "test-model", "messages": [{"role": "user", "content": "Hi"}]},
        headers=headers,
    )
    assert resp.status_code == 403


CHAT_COMPLETIONS_URL = "http://test-host/proxy/models/test-proj/chat/completions"
AUTH_HEADERS = {"Authorization": "Bearer token"}
ServiceHandler = Callable[[httpx.Request], Any]


@pytest.fixture
def mock_service() -> Generator[Callable[[ServiceHandler], None], None, None]:
    """Routes the requests that the proxy sends to the service to the given handler."""
    handlers: list[ServiceHandler] = []

    async def get_service_replica_client(*args, **kwargs) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handlers[0]), base_url="http://test-service"
        )

    with patch(
        "dstack._internal.proxy.lib.services.model_proxy.passthrough.get_service_replica_client",
        get_service_replica_client,
    ):
        yield handlers.append


async def make_repo() -> GatewayProxyRepo:
    repo = GatewayProxyRepo()
    await repo.set_project(make_project("test-proj"))
    await repo.set_service(make_service("test-proj", "test-service"))
    await repo.set_model(make_model("test-proj", "test-model", "test-service"))
    return repo


def sse(*chunks: dict, done: bool = True) -> bytes:
    events = [json.dumps(chunk, separators=(",", ":")) for chunk in chunks]
    if done:
        events.append("[DONE]")
    return "".join(f"data: {event}\n\n" for event in events).encode()


def parse_sse(content: bytes) -> list[Any]:
    events = content.decode().removesuffix("\n\n").split("\n\n")
    assert all(event.startswith("data: ") for event in events)
    assert events[-1] == "data: [DONE]"
    return [json.loads(event.removeprefix("data: ")) for event in events[:-1]]


def chunk(content: str, usage: Optional[dict] = None, index: int = 0) -> dict:
    result = {"id": "1", "choices": [{"index": index, "delta": {"content": content}}]}
    if usage is not None:
        result["usage"] = usage
    return result


def finish_chunk(index: int = 0) -> dict:
    return {"id": "1", "choices": [{"index": index, "delta": {}, "finish_reason": "stop"}]}


def usage(prompt_tokens: int, completion_tokens: int, cached_tokens: int = 0) -> dict:
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "prompt_tokens_details": {"cached_tokens": cached_tokens},
    }


@pytest.mark.asyncio
class TestChatCompletionsPassthrough:
    async def test_forwards_request_and_response_unchanged(self, mock_service) -> None:
        request_body = {
            "model": "test-model",
            "max_completion_tokens": 100,
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "Weather in Berlin?"}]},
                {"role": "assistant", "content": None, "tool_calls": [{"id": "call-1"}]},
                {"role": "tool", "tool_call_id": "call-1", "content": "Sunny"},
            ],
            "tools": [{"type": "function", "function": {"name": "get_weather"}}],
        }
        # Unusual spacing shows that the response is not parsed and serialized again.
        response_body = (
            b'{"id": "1",  "choices": [{"message": {"content": "Sunny", "reasoning": "..."}}],'
            b' "usage": {"prompt_tokens": 812, "completion_tokens": 140, "total_tokens": 952,'
            b' "prompt_tokens_details": {"cached_tokens": 768}}}'
        )
        requests = []

        def handle(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200, content=response_body, headers={"content-type": "application/json"}
            )

        mock_service(handle)
        auth = ProxyTestAuthProvider({"test-proj": {"token"}})
        meter = ProxyTestMeter()
        repo = await make_repo()
        service = await repo.get_service("test-proj", "test-service")
        assert service is not None
        client = make_http_client(repo, auth, meter)
        resp = await client.post(CHAT_COMPLETIONS_URL, json=request_body, headers=AUTH_HEADERS)

        assert resp.status_code == 200
        assert resp.content == response_body
        assert resp.headers["content-type"] == "application/json"
        assert requests[0].url.path == "/v1/chat/completions"
        assert json.loads(requests[0].content) == request_body
        assert meter.added == [
            MeteredTokens(
                caller=make_caller("test-proj", "token"),
                service=service,
                export_id=None,
                input_tokens=812,
                cached_input_tokens=768,
                output_tokens=140,
            )
        ]

    async def test_passes_service_errors_through(self, mock_service) -> None:
        error = b'{"error": {"message": "Too many requests"}}'
        mock_service(
            lambda request: httpx.Response(429, content=error, headers={"Retry-After": "7"})
        )
        auth = ProxyTestAuthProvider({"test-proj": {"token"}})
        meter = ProxyTestMeter()
        client = make_http_client(await make_repo(), auth, meter)
        resp = await client.post(
            CHAT_COMPLETIONS_URL,
            json={"model": "test-model", "messages": [], "stream": True},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 429
        assert resp.content == error
        assert resp.headers["Retry-After"] == "7"
        assert meter.added == []

    async def test_json_response_to_stream_request_is_not_a_stream(self, mock_service) -> None:
        # A service that ignores `stream`
        response_body = json.dumps({"id": "1", "choices": [], "usage": usage(9, 2)}).encode()
        mock_service(
            lambda request: httpx.Response(
                200, content=response_body, headers={"content-type": "application/json"}
            )
        )
        auth = ProxyTestAuthProvider({"test-proj": {"token"}})
        meter = ProxyTestMeter()
        client = make_http_client(await make_repo(), auth, meter)
        request_body = {"model": "test-model", "messages": [], "stream": True}
        resp = await client.post(CHAT_COMPLETIONS_URL, json=request_body, headers=AUTH_HEADERS)

        assert resp.status_code == 200
        assert resp.content == response_body
        assert [(m.input_tokens, m.output_tokens) for m in meter.added] == [(9, 2)]

    async def test_does_not_meter_token_counts_that_are_not_real(self, mock_service) -> None:
        response_body = b'{"choices": [], "usage": {"prompt_tokens": 9223372036854775808}}'
        mock_service(lambda request: httpx.Response(200, content=response_body))
        auth = ProxyTestAuthProvider({"test-proj": {"token"}})
        meter = ProxyTestMeter()
        client = make_http_client(await make_repo(), auth, meter)
        resp = await client.post(
            CHAT_COMPLETIONS_URL,
            json={"model": "test-model", "messages": []},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.content == response_body
        assert meter.added == []

    @pytest.mark.parametrize(
        ("stream_options", "expected_usage"),
        [
            pytest.param(None, [None, None], id="client-set-nothing"),
            pytest.param(
                {"include_usage": True}, [None, None, usage(9, 2, 4)], id="include-usage"
            ),
            pytest.param(
                {"include_usage": True, "continuous_usage_stats": True},
                [usage(9, 1), usage(9, 2), usage(9, 2, 4)],
                id="include-and-continuous-usage",
            ),
        ],
    )
    async def test_stream_has_only_usage_that_client_asked_for(
        self, mock_service, stream_options: Optional[dict], expected_usage: list[Optional[dict]]
    ) -> None:
        requests = []

        def handle(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                content=sse(
                    chunk("Hello", usage(9, 1)),
                    chunk(" there", usage(9, 2)),
                    {"id": "1", "choices": [], "usage": usage(9, 2, 4)},
                ),
                headers={"content-type": "text/event-stream"},
            )

        mock_service(handle)
        auth = ProxyTestAuthProvider({"test-proj": {"token"}})
        meter = ProxyTestMeter()
        client = make_http_client(await make_repo(), auth, meter)
        request_body: dict = {"model": "test-model", "messages": [], "stream": True}
        if stream_options is not None:
            request_body["stream_options"] = stream_options
        resp = await client.post(CHAT_COMPLETIONS_URL, json=request_body, headers=AUTH_HEADERS)

        assert resp.status_code == 200
        chunks = parse_sse(resp.content)
        assert [c["choices"][0]["delta"]["content"] for c in chunks[:2]] == ["Hello", " there"]
        assert [c.get("usage") for c in chunks] == expected_usage
        # The service is always asked for token counts on every chunk.
        assert json.loads(requests[0].content)["stream_options"] == {
            "include_usage": True,
            "continuous_usage_stats": True,
        }
        # Tokens are metered as they are counted: each chunk adds what is new.
        assert [(m.input_tokens, m.cached_input_tokens, m.output_tokens) for m in meter.added] == [
            (9, 0, 1),
            (0, 0, 1),
            (0, 4, 0),
        ]

    async def test_stream_has_last_usage_that_service_sent_with_choices(
        self, mock_service
    ) -> None:
        # Dynamo sends the last `usage` in the last chunk with choices
        mock_service(
            lambda request: httpx.Response(
                200, content=sse(chunk("Hello", usage(9, 1)), chunk(" there", usage(9, 2, 4)))
            )
        )
        auth = ProxyTestAuthProvider({"test-proj": {"token"}})
        client = make_http_client(await make_repo(), auth, ProxyTestMeter())
        request_body = {
            "model": "test-model",
            "messages": [],
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        resp = await client.post(CHAT_COMPLETIONS_URL, json=request_body, headers=AUTH_HEADERS)

        assert resp.status_code == 200
        chunks = parse_sse(resp.content)
        assert [c.get("usage") for c in chunks] == [None, None, usage(9, 2, 4)]
        assert chunks[2]["choices"] == []

    async def test_stream_has_chunk_without_choices_and_usage(self, mock_service) -> None:
        # SGLang sends its `sglext` in such a chunk
        sglext = {"cached_tokens_details": {"device": 4}}
        mock_service(
            lambda request: httpx.Response(
                200,
                content=sse(
                    chunk("Hello", usage(9, 1)),
                    {"id": "1", "choices": [], "usage": None, "sglext": sglext},
                    {"id": "1", "choices": [], "usage": usage(9, 1)},
                ),
            )
        )
        auth = ProxyTestAuthProvider({"test-proj": {"token"}})
        client = make_http_client(await make_repo(), auth, ProxyTestMeter())
        request_body = {"model": "test-model", "messages": [], "stream": True}
        resp = await client.post(CHAT_COMPLETIONS_URL, json=request_body, headers=AUTH_HEADERS)

        assert resp.status_code == 200
        assert parse_sse(resp.content) == [
            chunk("Hello"),
            {"id": "1", "choices": [], "sglext": sglext},
        ]

    @pytest.mark.parametrize(
        ("rest", "error", "expected_rest_chunks", "expected_message"),
        [
            pytest.param(
                b'data: {"id":"1","cho',
                None,
                [],
                "Error requesting model: the response ended before it was complete",
                id="ends-within-line",
            ),
            pytest.param(
                sse(chunk(" there"), done=False).removesuffix(b"\n"),
                None,
                [chunk(" there")],
                "Error requesting model: the response ended before it was complete",
                id="ends-within-event",
            ),
            pytest.param(
                sse(chunk("Hi", index=1), finish_chunk(index=0), done=False),
                None,
                [chunk("Hi", index=1), finish_chunk(index=0)],
                "Error requesting model: the response ended before it was complete",
                id="ends-before-every-choice-is-finished",
            ),
            pytest.param(
                b"",
                httpx.ReadError("broken"),
                [],
                "Error requesting model: ReadError('broken')",
                id="read-error",
            ),
        ],
    )
    async def test_stream_ends_with_error_if_response_is_not_complete(
        self,
        mock_service,
        rest: bytes,
        error: Optional[Exception],
        expected_rest_chunks: list[dict],
        expected_message: str,
    ) -> None:
        async def stream() -> AsyncIterator[bytes]:
            yield sse(chunk("Hello", usage(9, 1)), done=False) + rest
            if error is not None:
                raise error

        mock_service(lambda request: httpx.Response(200, content=stream()))
        auth = ProxyTestAuthProvider({"test-proj": {"token"}})
        meter = ProxyTestMeter()
        repo = await make_repo()
        client = make_http_client(repo, auth, meter)
        request_body = {"model": "test-model", "messages": [], "stream": True}
        resp = await client.post(CHAT_COMPLETIONS_URL, json=request_body, headers=AUTH_HEADERS)

        assert resp.status_code == 200
        events = [event for event in resp.content.decode().split("\n\n") if event.strip()]
        assert [json.loads(event.strip().removeprefix("data: ")) for event in events] == [
            chunk("Hello"),
            *expected_rest_chunks,
            {"error": {"message": expected_message, "code": 502}},
        ]
        assert [(m.input_tokens, m.output_tokens) for m in meter.added] == [(9, 1)]
        # OpenAI SDKs raise an error on the last event
        completion = await make_openai_client(repo, auth, "test-proj").chat.completions.create(
            model="test-model", messages=[], stream=True
        )
        with pytest.raises(openai.APIError, match=re.escape(expected_message)):
            async for _ in completion:
                pass

    @pytest.mark.parametrize(
        "error", [None, httpx.ReadError("broken")], ids=["service-closes-stream", "read-error"]
    )
    async def test_stream_without_done_is_complete_if_choices_are_finished(
        self, mock_service, error: Optional[Exception]
    ) -> None:
        content = sse(chunk("Hello"), finish_chunk(), done=False)

        async def stream() -> AsyncIterator[bytes]:
            yield content
            if error is not None:
                raise error

        mock_service(lambda request: httpx.Response(200, content=stream()))
        auth = ProxyTestAuthProvider({"test-proj": {"token"}})
        client = make_http_client(await make_repo(), auth, ProxyTestMeter())
        request_body = {"model": "test-model", "messages": [], "stream": True}
        resp = await client.post(CHAT_COMPLETIONS_URL, json=request_body, headers=AUTH_HEADERS)

        assert resp.status_code == 200
        assert resp.content == content

    async def test_meters_stopped_stream_up_to_its_last_chunk(self, mock_service) -> None:
        is_stream_closed = asyncio.Event()

        async def stream() -> AsyncIterator[bytes]:
            try:
                yield sse(chunk("Hello", usage(9, 1)), chunk(" there", usage(9, 2)), done=False)
                await asyncio.Event().wait()  # the model keeps generating
            finally:
                is_stream_closed.set()

        mock_service(lambda request: httpx.Response(200, content=stream()))
        meter = ProxyTestMeter()
        request = ASGIRequest(
            make_app(await make_repo(), ProxyTestAuthProvider({"test-proj": {"token"}}), meter),
            {"model": "test-model", "messages": [], "stream": True},
        )
        await asyncio.wait_for(request.is_body_received.wait(), timeout=10)
        request.disconnect()
        await asyncio.wait_for(request.wait(), timeout=10)

        await asyncio.wait_for(is_stream_closed.wait(), timeout=10)
        assert [(m.input_tokens, m.output_tokens) for m in meter.added] == [(9, 1), (0, 1)]

    @pytest.mark.parametrize("stream", [False, True])
    async def test_does_not_meter_request_stopped_before_response(
        self, mock_service, stream: bool
    ) -> None:
        is_request_received = asyncio.Event()
        is_request_cancelled = asyncio.Event()

        async def handle(request: httpx.Request) -> httpx.Response:
            is_request_received.set()
            try:
                await asyncio.Event().wait()  # the model is generating
            except asyncio.CancelledError:
                is_request_cancelled.set()
                raise
            raise AssertionError("unreachable")

        mock_service(handle)
        meter = ProxyTestMeter()
        request = ASGIRequest(
            make_app(await make_repo(), ProxyTestAuthProvider({"test-proj": {"token"}}), meter),
            {"model": "test-model", "messages": [], "stream": stream},
        )
        await asyncio.wait_for(is_request_received.wait(), timeout=10)
        request.disconnect()
        await asyncio.wait_for(request.wait(), timeout=10)

        assert is_request_cancelled.is_set()
        assert meter.added == []


@pytest.mark.asyncio
async def test_imported_model_is_served_to_importer_project_members_only(mock_service) -> None:
    mock_service(lambda request: httpx.Response(200, json={"usage": usage(9, 2)}))
    auth = ProxyTestAuthProvider(
        {"importer-proj": {"importer-token"}, "exporter-proj": {"exporter-token"}}
    )
    meter = ProxyTestMeter()
    service = make_service("exporter-proj", "test-service")
    repo = GatewayProxyRepo()
    await repo.set_project(make_project("exporter-proj"))
    await repo.set_service(service)
    await repo.set_model(make_model("exporter-proj", "test-model", "test-service"))
    await repo.set_import(
        ImportedModel(
            importer_project="importer-proj",
            export_id="export-1",
            exporter_project="exporter-proj",
            name="test-model",
        )
    )
    client = make_http_client(repo, auth, meter)
    body = {"model": "test-model", "messages": []}

    resp = await client.get(
        "http://test-host/proxy/models/importer-proj/models",
        headers={"Authorization": "Bearer importer-token"},
    )
    assert resp.status_code == 200
    assert [model["id"] for model in resp.json()["data"]] == ["test-model"]
    resp = await client.post(
        "http://test-host/proxy/models/importer-proj/chat/completions",
        json=body,
        headers={"Authorization": "Bearer importer-token"},
    )
    assert resp.status_code == 200
    # The request goes to the exporter project's service and is metered
    # under the importer project with the export.
    assert meter.added == [
        MeteredTokens(
            caller=make_caller("importer-proj", "importer-token"),
            service=service,
            export_id="export-1",
            input_tokens=9,
            cached_input_tokens=0,
            output_tokens=2,
        )
    ]

    for project_name, token in (
        ("importer-proj", "exporter-token"),
        ("exporter-proj", "importer-token"),
    ):
        resp = await client.post(
            f"http://test-host/proxy/models/{project_name}/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
    assert len(meter.added) == 1


@pytest.mark.asyncio
async def test_tgi_chat_completions_are_validated_and_not_metered(mock_chat_client) -> None:
    auth = ProxyTestAuthProvider({"test-proj": {"token"}})
    meter = ProxyTestMeter()
    repo = GatewayProxyRepo()
    await repo.set_project(make_project("test-proj"))
    await repo.set_service(make_service("test-proj", "test-service"))
    await repo.set_model(
        make_model("test-proj", "test-model", "test-service", format_spec=TGI_FORMAT)
    )
    client = make_http_client(repo, auth, meter)
    body = {"model": "test-model", "messages": [{"role": "user", "content": "Hi"}]}

    resp = await client.post(CHAT_COMPLETIONS_URL, json=body, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["usage"]["prompt_tokens"] == 9
    assert meter.added == []

    resp = await client.post(
        CHAT_COMPLETIONS_URL, json={**body, "max_completion_tokens": 100}, headers=AUTH_HEADERS
    )
    assert resp.status_code == 422


class ASGIRequest:
    """
    Sends a chat completions request to the app without an HTTP client,
    to control when the client disconnects.
    """

    def __init__(self, app: FastAPI, body: dict) -> None:
        self.status: Optional[int] = None
        self.is_body_received = asyncio.Event()
        self._body = json.dumps(body).encode()
        self._is_disconnected = asyncio.Event()
        scope: Scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "path": "/proxy/models/test-proj/chat/completions",
            "raw_path": b"/proxy/models/test-proj/chat/completions",
            "query_string": b"",
            "headers": [
                (b"authorization", b"Bearer token"),
                (b"content-type", b"application/json"),
            ],
        }
        self._task = asyncio.create_task(app(scope, self._receive, self._send))

    def disconnect(self) -> None:
        self._is_disconnected.set()

    async def wait(self) -> None:
        await self._task

    async def _receive(self) -> Message:
        if self._body:
            body, self._body = self._body, b""
            return {"type": "http.request", "body": body, "more_body": False}
        await self._is_disconnected.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            self.status = message["status"]
        elif message.get("body"):
            self.is_body_received.set()
