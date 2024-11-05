from datetime import datetime
from typing import AsyncIterator, Generator, Optional
from unittest.mock import patch

import openai
import pytest

from dstack._internal.proxy.repos.base import BaseProxyRepo, ChatModel, OpenAIChatModelFormat
from dstack._internal.proxy.schemas.model_proxy import (
    ChatCompletionsChoice,
    ChatCompletionsChunk,
    ChatCompletionsChunkChoice,
    ChatCompletionsRequest,
    ChatCompletionsResponse,
    ChatCompletionsUsage,
    ChatMessage,
)
from dstack._internal.proxy.services.model_proxy.clients import ChatCompletionsClient
from dstack._internal.proxy.testing.common import make_app_client, make_project, make_service
from dstack._internal.proxy.testing.repo import ProxyTestRepo

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
    name: str, run_name: str, created_at: datetime = datetime.fromtimestamp(0)
) -> ChatModel:
    return ChatModel(
        name=name,
        created_at=created_at,
        run_name=run_name,
        format_spec=OpenAIChatModelFormat(format="openai", prefix="/v1"),
    )


def make_openai_client(
    repo: BaseProxyRepo, project_name: str, auth_token: Optional[str] = None
) -> openai.AsyncOpenAI:
    _, http_client = make_app_client(repo, auth_token="token")
    return openai.AsyncOpenAI(
        api_key=auth_token,
        base_url=f"http://test-host/proxy/models/{project_name}",
        http_client=http_client,
    )


@pytest.fixture
def mock_chat_client() -> Generator[None, None, None]:
    with (
        patch(
            "dstack._internal.proxy.services.service_connection.ServiceReplicaConnectionPool.add"
        ),
        patch("dstack._internal.proxy.routers.model_proxy.get_chat_client") as get_client_mock,
    ):
        get_client_mock.return_value = ChatClientStub()
        yield


@pytest.mark.asyncio
async def test_list_models() -> None:
    repo = ProxyTestRepo(project_to_tokens={"test-proj": {"token"}})
    await repo.add_project(make_project("test-proj"))
    await repo.add_service(project_name="test-proj", service=make_service("test-service-1"))
    await repo.add_service(project_name="test-proj", service=make_service("test-service-2"))
    await repo.add_model(
        project_name="test-proj",
        model=make_model("test-model-1", "test-service-1", created_at=datetime.fromtimestamp(123)),
    )
    await repo.add_model(
        project_name="test-proj",
        model=make_model("test-model-2", "test-service-2", created_at=datetime.fromtimestamp(321)),
    )
    _, client = make_app_client(repo, auth_token="token")

    client = make_openai_client(repo, "test-proj", auth_token="token")
    models = [model async for model in client.models.list()]

    assert models[0].id == "test-model-1"
    assert models[0].created == 123
    assert models[0].owned_by == "test-proj"
    assert models[1].id == "test-model-2"
    assert models[1].created == 321
    assert models[1].owned_by == "test-proj"


@pytest.mark.asyncio
async def test_list_models_empty() -> None:
    repo = ProxyTestRepo(project_to_tokens={"test-proj": {"token"}, "test-proj-empty": {"token"}})
    await repo.add_project(make_project("test-proj"))
    await repo.add_project(make_project("test-proj-empty"))
    await repo.add_service(project_name="test-proj", service=make_service("test-service"))
    await repo.add_model(project_name="test-proj", model=make_model("test-model", "test-service"))
    _, client = make_app_client(repo, auth_token="token")

    client = make_openai_client(repo, "test-proj-empty", auth_token="token")
    models = [model async for model in client.models.list()]
    assert not models


@pytest.mark.asyncio
async def test_chat_completions(mock_chat_client) -> None:
    repo = ProxyTestRepo(project_to_tokens={"test-proj": {"token"}})
    await repo.add_project(make_project("test-proj"))
    await repo.add_service(project_name="test-proj", service=make_service("test-service"))
    await repo.add_model(project_name="test-proj", model=make_model("test-model", "test-service"))
    client = make_openai_client(repo, "test-proj", auth_token="token")
    completion = await client.chat.completions.create(
        model="test-model",
        messages=[{"role": "user", "content": "Hi"}],
    )
    assert completion.choices[0].message.content == SAMPLE_RESPONSE


@pytest.mark.asyncio
async def test_chat_completions_stream(mock_chat_client) -> None:
    repo = ProxyTestRepo(project_to_tokens={"test-proj": {"token"}})
    await repo.add_project(make_project("test-proj"))
    await repo.add_service(project_name="test-proj", service=make_service("test-service"))
    await repo.add_model(project_name="test-proj", model=make_model("test-model", "test-service"))
    client = make_openai_client(repo, "test-proj", auth_token="token")
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
    repo = ProxyTestRepo(project_to_tokens={"test-proj": {"token"}})
    await repo.add_project(make_project("test-proj"))
    client = make_openai_client(repo, "test-proj", auth_token="token")
    with pytest.raises(openai.NotFoundError):
        await client.chat.completions.create(
            model="unknown-model",
            messages=[{"role": "user", "content": "Hi"}],
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("token", ["wrong-token", ""])
async def test_unauthorized(token: str) -> None:
    repo = ProxyTestRepo(project_to_tokens={"test-proj": {"correct-token"}})
    await repo.add_project(make_project("test-proj"))
    client = make_openai_client(repo, "test-proj", auth_token=token)

    with pytest.raises(openai.PermissionDeniedError):
        await client.models.list()
    with pytest.raises(openai.PermissionDeniedError):
        await client.chat.completions.create(
            model="test-model",
            messages=[{"role": "user", "content": "Hi"}],
        )


@pytest.mark.asyncio
async def test_no_token() -> None:
    repo = ProxyTestRepo(project_to_tokens={"test-proj": {"correct-token"}})
    await repo.add_project(make_project("test-proj"))
    _, client = make_app_client(repo, auth_token=None)

    resp = await client.get("http://test-host/proxy/models/test-proj/models")
    assert resp.status_code == 403

    resp = await client.post(
        "http://test-host/proxy/models/test-proj/chat/completions",
        json={"model": "test-model", "messages": [{"role": "user", "content": "Hi"}]},
    )
    assert resp.status_code == 403
