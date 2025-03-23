from typing import Any, Dict, List, Literal, Optional, Union

from dstack._internal.core.models.common import CoreModel


class ChatMessage(CoreModel):
    role: str  # TODO(egor-s) types
    content: str


class ChatCompletionsRequest(CoreModel):
    messages: List[ChatMessage]
    model: str
    frequency_penalty: Optional[float] = 0.0
    logit_bias: Dict[str, float] = {}
    max_tokens: Optional[int] = None
    n: int = 1
    presence_penalty: float = 0.0
    response_format: Optional[Dict] = None
    seed: Optional[int] = None
    stop: Optional[Union[str, List[str]]] = None
    stream: bool = False
    temperature: Optional[float] = 1.0
    top_p: Optional[float] = 1.0
    tools: List[Any] = []
    tool_choice: Union[Literal["none", "auto"], Dict] = {}
    user: Optional[str] = None


class ChatCompletionsChoice(CoreModel):
    finish_reason: str
    index: int
    message: ChatMessage


class ChatCompletionsChunkChoice(CoreModel):
    delta: object
    logprobs: object = {}
    finish_reason: Optional[str]
    index: int


class ChatCompletionsUsage(CoreModel):
    completion_tokens: int
    prompt_tokens: int
    total_tokens: int


class ChatCompletionsResponse(CoreModel):
    id: str
    choices: List[ChatCompletionsChoice]
    created: int
    model: str
    system_fingerprint: str = ""
    object: Literal["chat.completion"] = "chat.completion"
    usage: ChatCompletionsUsage


class ChatCompletionsChunk(CoreModel):
    id: Optional[str] = None
    choices: List[ChatCompletionsChunkChoice]
    created: Optional[int] = None
    model: str
    system_fingerprint: Optional[str] = ""
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"


class Model(CoreModel):
    object: Literal["model"] = "model"
    id: str
    created: int
    owned_by: str


class ModelsResponse(CoreModel):
    object: Literal["list"] = "list"
    data: List[Model]
