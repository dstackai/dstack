import datetime
from enum import Enum
from typing import Optional, Union

from pydantic import Field
from typing_extensions import Annotated, Literal

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel


class GatewayStatus(str, Enum):
    SUBMITTED = "submitted"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    FAILED = "failed"


class LetsEncryptGatewayCertificate(CoreModel):
    type: Annotated[
        Literal["lets-encrypt"], Field(description="Automatic certificates by Let's Encrypt")
    ] = "lets-encrypt"


class ACMGatewayCertificate(CoreModel):
    type: Annotated[
        Literal["acm"], Field(description="Certificates by AWS Certificate Manager (ACM)")
    ] = "acm"
    arn: Annotated[
        str, Field(description="The ARN of the wildcard ACM certificate for the domain")
    ]


# TODO: Allow setting up custom ACME certificate (e.g. ZeroSSL) via GatewayConfiguration

AnyGatewayCertificate = Union[LetsEncryptGatewayCertificate, ACMGatewayCertificate]


class GatewayCertificate(CoreModel):
    __root__: Annotated[
        AnyGatewayCertificate,
        Field(discriminator="type"),
    ]


class GatewayConfiguration(CoreModel):
    type: Literal["gateway"] = "gateway"
    name: Annotated[Optional[str], Field(description="The gateway name")] = None
    default: Annotated[bool, Field(description="Make the gateway default")] = False
    backend: Annotated[BackendType, Field(description="The gateway backend")]
    region: Annotated[str, Field(description="The gateway region")]
    domain: Annotated[
        Optional[str], Field(description="The gateway domain, e.g. `example.com`")
    ] = None
    public_ip: Annotated[bool, Field(description="Allocate public IP for the gateway")] = True
    certificate: Annotated[
        Optional[AnyGatewayCertificate],
        Field(description="The SSL certificate configuration. Defaults to `type: lets-encrypt`"),
    ] = LetsEncryptGatewayCertificate()


class Gateway(CoreModel):
    name: str
    configuration: GatewayConfiguration
    created_at: datetime.datetime
    status: GatewayStatus
    status_message: Optional[str]
    # The ip address / hostname the user should set up the domain for.
    # Could be the same as ip_address but also different, e.g. gateway behind ALB.
    hostname: Optional[str]
    # The ip address of the gateway instance
    ip_address: Optional[str]
    instance_id: Optional[str]
    # TODO: configuration fields are duplicated on top-level for backward compatibility with 0.18.x
    # Remove in 0.19
    backend: BackendType
    region: str
    default: bool
    wildcard_domain: Optional[str]


class GatewayComputeConfiguration(CoreModel):
    project_name: str
    instance_name: str
    backend: BackendType
    region: str
    public_ip: bool
    ssh_key_pub: str
    certificate: Optional[AnyGatewayCertificate]


class GatewayProvisioningData(CoreModel):
    instance_id: str
    ip_address: str
    region: str
    availability_zone: Optional[str] = None
    hostname: Optional[str] = None
    backend_data: Optional[str] = None  # backend-specific data in json


class BaseChatModel(CoreModel):
    type: Annotated[Literal["chat"], Field(description="The type of the model")]
    name: Annotated[str, Field(description="The name of the model")]
    format: Annotated[
        str, Field(description="The serving format. Supported values include `openai` and `tgi`")
    ]


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
