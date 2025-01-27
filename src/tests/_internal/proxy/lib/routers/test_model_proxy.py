from datetime import datetime
from typing import AsyncIterator, Generator
from unittest.mock import patch

import httpx
import openai
import pytest
from fastapi import FastAPI

from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.lib.auth import BaseProxyAuthProvider
from dstack._internal.proxy.lib.models import ChatModel, OpenAIChatModelFormat
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
from dstack._internal.proxy.lib.testing.auth import ProxyTestAuthProvider
from dstack._internal.proxy.lib.testing.common import (
    ProxyTestDependencyInjector,
    make_project,
    make_service,
)

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


def make_model(
    project_name: str, name: str, run_name: str, created_at: datetime = datetime.fromtimestamp(0)
) -> ChatModel:
    return ChatModel(
        project_name=project_name,
        name=name,
        created_at=created_at,
        run_name=run_name,
        format_spec=OpenAIChatModelFormat(format="openai", prefix="/v1"),
    )


def make_http_client(repo: BaseProxyRepo, auth: BaseProxyAuthProvider) -> httpx.AsyncClient:
    app = FastAPI()
    app.state.proxy_dependency_injector = ProxyTestDependencyInjector(repo=repo, auth=auth)
    app.include_router(router, prefix="/proxy/models")
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app))


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
    await repo.set_model(make_model("test-proj", "test-model", "test-service"))
    client = make_openai_client(repo, auth, "test-proj", auth_token="token")
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
    await repo.set_model(make_model("test-proj", "test-model", "test-service"))
    client = make_openai_client(repo, auth, "test-proj", auth_token="token")
    response = await client.chat.completions.create(
        model="test-model",
        messages=[{"role": "user", "content": "Hi"}],
        stream=True,
    )
    completion = ""
    async for chunk in response:
        completion += chunk.choices[0].delta.content
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
@pytest.mark.parametrize("token", ["wrong-token", ""])
async def test_unauthorized(token: str) -> None:
    auth = ProxyTestAuthProvider({"test-proj": {"correct-token"}})
    repo = GatewayProxyRepo()
    await repo.set_project(make_project("test-proj"))
    client = make_openai_client(repo, auth, "test-proj", auth_token=token)

    with pytest.raises(openai.PermissionDeniedError):
        await client.models.list()
    with pytest.raises(openai.PermissionDeniedError):
        await client.chat.completions.create(
            model="test-model",
            messages=[{"role": "user", "content": "Hi"}],
        )


@pytest.mark.asyncio
async def test_no_token() -> None:
    auth = ProxyTestAuthProvider({"test-proj": {"correct-token"}})
    repo = GatewayProxyRepo()
    await repo.set_project(make_project("test-proj"))
    client = make_http_client(repo, auth)

    resp = await client.get("http://test-host/proxy/models/test-proj/models")
    assert resp.status_code == 403

    resp = await client.post(
        "http://test-host/proxy/models/test-proj/chat/completions",
        json={"model": "test-model", "messages": [{"role": "user", "content": "Hi"}]},
    )
    assert resp.status_code == 403
