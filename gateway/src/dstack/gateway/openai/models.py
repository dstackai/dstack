from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class BaseChatModel(BaseModel):
    type: Literal["chat"]
    name: str
    format: str


class TGIChatModel(BaseChatModel):
    format: Literal["tgi"]
    chat_template: str
    eos_token: str


class OpenAIChatModel(BaseChatModel):
    format: Literal["openai"]
    prefix: str


ChatModel = Annotated[Union[TGIChatModel, OpenAIChatModel], Field(discriminator="format")]
AnyModel = Union[ChatModel]  # embeddings and etc.


class OpenAIOptions(BaseModel):
    model: AnyModel  # TODO(egor-s): add discriminator by type


class ServiceModel(BaseModel):
    model: AnyModel
    domain: str
    created: int
