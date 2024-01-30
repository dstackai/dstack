import datetime
from typing import Optional, Union

from pydantic import BaseModel, Field
from typing_extensions import Annotated, Literal

from dstack._internal.core.models.backends.base import BackendType


class Gateway(BaseModel):
    name: str
    ip_address: Optional[str]
    instance_id: Optional[str]
    region: str
    wildcard_domain: Optional[str]
    default: bool
    created_at: datetime.datetime
    backend: BackendType


class BaseChatModel(BaseModel):
    type: Annotated[Literal["chat"], Field(description="The type of the model")]
    name: Annotated[str, Field(description="The name of the model")]
    format: Annotated[str, Field(description="The serving format")]


class TGIChatModel(BaseChatModel):
    """
    Mapping of the model for the OpenAI-compatible endpoint.

    Attributes:
        type (str): The type of the model, e.g. "chat"
        name (str): The name of the model. This name will be used both to load model configuration from the HuggingFace Hub and in the OpenAI-compatible endpoint.
        format (str): The format of the model, e.g. "tgi" if the model is served with HuggingFace's Text Generation Inference.
        chat_template (Optional[str]): The custom prompt template for the model. If not specified, the default prompt template the HuggingFace Hub configuration will be used.
        eos_token (Optional[str]): The custom end of sentence token. If not specified, the default custom end of sentence token from the HuggingFace Hub configuration will be used.
    """

    format: Literal["tgi"]
    chat_template: Optional[str] = None  # will be set before registering the service
    eos_token: Optional[str] = None


class OpenAIChatModel(BaseChatModel):
    """
    Mapping of the model for the OpenAI-compatible endpoint.

    Attributes:
        type (str): The type of the model, e.g. "chat"
        name (str): The name of the model. This name will be used both to load model configuration from the HuggingFace Hub and in the OpenAI-compatible endpoint.
        format (str): The format of the model, i.e. "openai".
        prefix (str): The `base_url` prefix: `http://hostname/{prefix}/chat/completions`. Defaults to `/v1`.
    """

    format: Literal["openai"]
    prefix: Annotated[str, Field(description="The `base_url` prefix (after hostname)")] = "/v1"


ChatModel = Annotated[Union[TGIChatModel, OpenAIChatModel], Field(discriminator="format")]
AnyModel = Annotated[Union[ChatModel], Field(discriminator="type")]  # embeddings and etc.
