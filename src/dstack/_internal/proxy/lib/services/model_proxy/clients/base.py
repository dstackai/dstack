from abc import ABC, abstractmethod
from typing import AsyncIterator

from dstack._internal.proxy.lib.schemas.model_proxy import (
    ChatCompletionsChunk,
    ChatCompletionsRequest,
    ChatCompletionsResponse,
)


class ChatCompletionsClient(ABC):
    @abstractmethod
    async def generate(self, request: ChatCompletionsRequest) -> ChatCompletionsResponse:
        pass

    @abstractmethod
    async def stream(self, request: ChatCompletionsRequest) -> AsyncIterator[ChatCompletionsChunk]:
        yield
