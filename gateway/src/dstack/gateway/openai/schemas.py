from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel

FinishReason = Literal["stop", "length", "tool_calls"]


class ChatMessage(BaseModel):
    role: str  # TODO(egor-s) types
    content: str


class ChatCompletionsRequest(BaseModel):
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
    tools: List = []
    tool_choice: Union[Literal["none", "auto"], Dict] = {}
    user: Optional[str] = None


class ChatCompletionsChoice(BaseModel):
    finish_reason: FinishReason
    index: int
    message: ChatMessage


class ChatCompletionsChunkChoice(BaseModel):
    delta: object
    logprobs: object = {}
    finish_reason: Optional[FinishReason]
    index: int


class ChatCompletionsUsage(BaseModel):
    completion_tokens: int
    prompt_tokens: int
    total_tokens: int


class ChatCompletionsResponse(BaseModel):
    id: str
    choices: List[ChatCompletionsChoice]
    created: int
    model: str
    system_fingerprint: str = ""
    object: Literal["chat.completion"] = "chat.completion"
    usage: ChatCompletionsUsage


class ChatCompletionsChunk(BaseModel):
    id: str
    choices: List[ChatCompletionsChunkChoice]
    created: int
    model: str
    system_fingerprint: str = ""
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"


class Model(BaseModel):
    object: Literal["model"] = "model"
    id: str
    created: int
    owned_by: str


class ModelsResponse(BaseModel):
    object: Literal["list"] = "list"
    data: List[Model]
