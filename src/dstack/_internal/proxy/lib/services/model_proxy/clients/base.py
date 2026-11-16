from abc import ABC, abstractmethod
from typing import AsyncIterator

from dstack._internal.proxy.lib.schemas.model_proxy import (
    ChatCompletionsChunk,
    ChatCompletionsRequest,
    ChatCompletionsResponse,
)
from dstack._internal.proxy.lib.services.usage import UsageAttempt


class ChatCompletionsClient(ABC):
    @abstractmethod
    async def generate(
        self, request: ChatCompletionsRequest, *, attempt: UsageAttempt | None = None
    ) -> ChatCompletionsResponse:
        pass

    @abstractmethod
    async def stream(
        self, request: ChatCompletionsRequest, *, attempt: UsageAttempt | None = None
    ) -> AsyncIterator[ChatCompletionsChunk]:
        yield
