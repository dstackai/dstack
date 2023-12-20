from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

ANY_MODEL = Union["ChatModel"]


class OpenAIOptions(BaseModel):
    model: Annotated[ANY_MODEL, Field(discriminator="type")]


class ServiceModel(BaseModel):
    model: ANY_MODEL
    domain: str
    created: int


class ChatModel(BaseModel):
    type: Literal["chat"] = "chat"
    name: str
    format: Literal["tgi"]
    chat_template: str
    eos_token: str
