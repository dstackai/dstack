import json

import httpx
import pytest
from fastapi import FastAPI

from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.gateway.services.metering import MeteringCollector
from dstack._internal.proxy.gateway.services.metering_store import MeteringStore
from dstack._internal.proxy.lib.auth import BaseProxyAuthProvider
from dstack._internal.proxy.lib.errors import ProxyError
from dstack._internal.proxy.lib.models import ChatModel, OpenAIChatModelFormat
from dstack._internal.proxy.lib.routers.model_proxy import router as model_router
from dstack._internal.proxy.lib.schemas.model_proxy import ChatCompletionsRequest
from dstack._internal.proxy.lib.schemas.usage import AuthorizedSubject, UsageKey
from dstack._internal.proxy.lib.services.model_proxy.clients.openai import OpenAIChatCompletions
from dstack._internal.proxy.lib.services.usage import VLLM_PROFILE
from dstack._internal.proxy.lib.testing.common import ProxyTestDependencyInjector, make_service
from tests._internal.proxy.gateway.services.test_metering import FakeClock

USAGE = {
    "prompt_tokens": 20,
    "completion_tokens": 3,
    "total_tokens": 23,
    "prompt_tokens_details": {"cached_tokens": 5},
}


class FragmentedStream(httpx.AsyncByteStream):
    def __init__(self, data):
        self.data = data
        self.closed = False

    async def __aiter__(self):
        for offset in range(0, len(self.data), 3):
            yield self.data[offset : offset + 3]

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
@pytest.mark.parametrize("stream,include_usage", [(False, False), (True, True), (True, False)])
async def test_backend_usage_is_observed_and_forwarded(tmp_path, stream, include_usage):
    clock = FakeClock()
    c = MeteringCollector(
        MeteringStore(tmp_path / "usage.json"), clock=clock, profiles={"s": VLLM_PROFILE}
    )
    await c.start()
    attempt = c.start_attempt(UsageKey(consumer_subject_id="u", service_id="s"), VLLM_PROFILE)
    requests = []
    response = {"id": "answer", "created": 1, "model": "test", "choices": [], "usage": USAGE}
    content = {"model": "test", "choices": [{"index": 0, "delta": {"content": "Hello"}}]}
    wire = (
        "data: "
        + json.dumps(content)
        + "\n\n"
        + "data: "
        + json.dumps(response)
        + "\n\n"
        + "data: "
        + json.dumps(response)
        + "\n\ndata: [DONE]\n\n"
    ).encode()
    transport_stream = FragmentedStream(wire)

    def backend(request):
        requests.append(json.loads(request.content))
        return (
            httpx.Response(200, stream=transport_stream)
            if stream
            else httpx.Response(200, json=response)
        )

    request = ChatCompletionsRequest.model_validate(
        {
            "model": "test",
            "messages": [],
            "stream": stream,
            "stream_options": {"include_usage": include_usage},
        }
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(backend), base_url="http://backend"
    ) as http:
        client = OpenAIChatCompletions(http, "/v1")
        if stream:
            chunks = [chunk async for chunk in client.stream(request, attempt=attempt)]
            assert requests[0]["stream_options"]["include_usage"] is True
            assert request.stream_options is not None
            assert request.stream_options.include_usage is include_usage
            assert len(chunks) == (3 if include_usage else 1)
            if include_usage:
                usage = chunks[-1].usage
                assert usage is not None and usage.prompt_tokens_details is not None
                assert usage.prompt_tokens_details.cached_tokens == 5
            assert transport_stream.closed
        else:
            result = await client.generate(request, attempt=attempt)
            assert result.usage.prompt_tokens_details is not None
            assert result.usage.prompt_tokens_details.cached_tokens == 5
    await attempt.finish()
    await attempt.finish()
    clock.advance()
    await c.rotate_if_due()
    entry = (await c.get_batches()).batches[0].entries[0]
    assert (
        entry.prompt_tokens,
        entry.cached_prompt_tokens,
        entry.completion_tokens,
        entry.total_tokens,
    ) == (20, 5, 3, 23)
    assert entry.unknown_usage_attempts == 0
    await c.close()


@pytest.mark.asyncio
async def test_truncated_stream_is_unknown_not_synthetic_done(tmp_path):
    clock = FakeClock()
    c = MeteringCollector(
        MeteringStore(tmp_path / "usage.json"), clock=clock, profiles={"s": VLLM_PROFILE}
    )
    await c.start()
    attempt = c.start_attempt(UsageKey(consumer_subject_id="u", service_id="s"), VLLM_PROFILE)
    stream = FragmentedStream(b'data: {"model":"test","choices":[]}\n\n')
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=stream)),
        base_url="http://backend",
    ) as http:
        client = OpenAIChatCompletions(http, "/v1")
        with pytest.raises(ProxyError):
            [
                chunk
                async for chunk in client.stream(
                    ChatCompletionsRequest(model="test", messages=[], stream=True), attempt=attempt
                )
            ]
    await attempt.finish()
    clock.advance()
    await c.rotate_if_due()
    entry = (await c.get_batches()).batches[0].entries[0]
    assert entry.unknown_usage_attempts == 1 and entry.total_tokens == 0
    assert stream.closed
    await c.close()


class IdentityProvider(BaseProxyAuthProvider):
    async def is_project_member(self, project_name, token):
        return token == "token"

    async def resolve_subject(self, project_name, token):
        return AuthorizedSubject(consumer_subject_id="verified-user") if token == "token" else None


class MeteredInjector(ProxyTestDependencyInjector):
    def __init__(self, repo, collector):
        super().__init__(repo, IdentityProvider())
        self.collector = collector

    def get_usage_observer(self):
        return self.collector


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stream,metadata",
    [
        pytest.param(False, {}, id="json"),
        pytest.param(False, {"system_fingerprint": None}, id="json-null-fingerprint"),
        pytest.param(True, {}, id="stream"),
    ],
)
async def test_model_handler_finalizes_verified_usage(tmp_path, monkeypatch, stream, metadata):
    clock = FakeClock()
    collector = MeteringCollector(
        MeteringStore(tmp_path / "usage.json"), clock=clock, profiles={"s": VLLM_PROFILE}
    )
    await collector.start()
    repo = GatewayProxyRepo()
    await repo.set_service(make_service("p", "run", run_id="s"))
    await repo.set_model(
        ChatModel(
            project_name="p",
            name="test",
            run_name="run",
            created_at=clock.utc_now(),
            format_spec=OpenAIChatModelFormat(format="openai", prefix="/v1"),
        )
    )
    app = FastAPI()
    app.state.proxy_dependency_injector = MeteredInjector(repo, collector)
    app.include_router(model_router, prefix="/models")
    response = {"id": "answer", "created": 1, "model": "test", "choices": [], "usage": USAGE}
    response.update(metadata)
    wire = ("data: " + json.dumps(response) + "\n\ndata: [DONE]\n\n").encode()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, stream=FragmentedStream(wire))
            if stream
            else httpx.Response(200, json=response)
        ),
        base_url="http://backend",
    ) as backend:

        async def connection(*args, **kwargs):
            return backend

        monkeypatch.setattr(
            "dstack._internal.proxy.lib.routers.model_proxy.get_service_replica_client", connection
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway"
        ) as client:
            result = await client.post(
                "/models/p/chat/completions",
                headers={"Authorization": "Bearer token", "consumer_subject_id": "spoofed"},
                json={
                    "model": "test",
                    "messages": [],
                    "stream": stream,
                    "stream_options": {"include_usage": True},
                    "user": "spoofed",
                },
            )
            assert result.status_code == 200
            if stream:
                assert '"cached_tokens":5' in result.text
            else:
                assert result.json()["system_fingerprint"] == metadata.get(
                    "system_fingerprint", ""
                )
                assert result.json()["usage"] == USAGE
    clock.advance()
    await collector.rotate_if_due()
    batches = (await collector.get_batches()).batches
    assert len(batches) == 1
    assert batches[0].entries[0].consumer_subject_id == "verified-user"
    assert batches[0].entries[0].cached_prompt_tokens == 5
    assert batches[0].entries[0].total_tokens == 23
    await collector.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("intermediate_only", [True, False])
async def test_confirmed_final_usage_survives_invalid_duplicates(tmp_path, intermediate_only):
    clock = FakeClock()
    collector = MeteringCollector(
        MeteringStore(tmp_path / "usage.json"), clock=clock, profiles={"s": VLLM_PROFILE}
    )
    await collector.start()
    attempt = collector.start_attempt(
        UsageKey(consumer_subject_id="u", service_id="s"), VLLM_PROFILE
    )
    final = {"model": "test", "choices": [], "usage": USAGE}
    if intermediate_only:
        events = [
            {**final, "choices": [{"index": 0, "delta": {"content": "Hi"}, "finish_reason": None}]}
        ]
    else:
        events = [
            final,
            {**final, "usage": {**USAGE, "completion_tokens": -1, "total_tokens": 19}},
        ]
    wire = "".join("data: " + json.dumps(event) + "\n\n" for event in events)
    if not intermediate_only:
        wire += "data: [DONE]\n\n"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, stream=FragmentedStream(wire.encode()))
        ),
        base_url="http://backend",
    ) as http:
        client = OpenAIChatCompletions(http, "/v1")
        request = ChatCompletionsRequest(model="test", messages=[], stream=True)
        if intermediate_only:
            with pytest.raises(ProxyError):
                [chunk async for chunk in client.stream(request, attempt=attempt)]
        else:
            [chunk async for chunk in client.stream(request, attempt=attempt)]
    await attempt.finish()
    clock.advance()
    await collector.rotate_if_due()
    entry = (await collector.get_batches()).batches[0].entries[0]
    await collector.close()
    if intermediate_only:
        assert entry.unknown_usage_attempts == 1 and entry.total_tokens == 0
    else:
        assert entry.unknown_usage_attempts == 0 and entry.total_tokens == 23
        assert entry.cached_prompt_tokens == 5
