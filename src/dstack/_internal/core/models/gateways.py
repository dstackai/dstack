import datetime
from typing import Optional, Union

from pydantic import Field
from typing_extensions import Annotated, Literal

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel


class GatewayConfiguration(CoreModel):
    type: Literal["gateway"] = "gateway"
    name: Annotated[Optional[str], Field(description="The gateway name")] = None
    default: Annotated[bool, Field(description="Make the gateway default")] = False
    backend: Annotated[BackendType, Field(description="The gateway backend")]
    region: Annotated[str, Field(description="The gateway region")]
    domain: Annotated[
        Optional[str], Field(description="The gateway domain, e.g. `*.example.com`")
    ] = None
    public_ip: Annotated[bool, Field(description="Allocate public IP for the gateway")] = True


class GatewayComputeConfiguration(CoreModel):
    project_name: str
    instance_name: str
    backend: BackendType
    region: str
    public_ip: bool
    ssh_key_pub: str


class Gateway(CoreModel):
    # TODO: configuration fields are duplicated on top-level for backward compatibility with 0.18.x
    # Remove in 0.19
    name: str
    ip_address: Optional[str]
    instance_id: Optional[str]
    region: str
    wildcard_domain: Optional[str]
    default: bool
    created_at: datetime.datetime
    backend: BackendType
    configuration: GatewayConfiguration


class BaseChatModel(CoreModel):
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
