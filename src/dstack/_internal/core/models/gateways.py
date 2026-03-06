import datetime
import uuid
from enum import Enum
from typing import Dict, Optional, Union

from pydantic import Field, validator
from typing_extensions import Annotated, Literal

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.routers import AnyGatewayRouterConfig
from dstack._internal.utils.tags import tags_validator


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
    instance_type: Annotated[
        Optional[str],
        Field(
            description=(
                "Backend-specific instance type to use for the gateway instance."
                " Omit to use the backend's default, which is typically a small non-GPU instance"
            ),
            min_length=1,
        ),
    ] = None
    router: Annotated[
        Optional[AnyGatewayRouterConfig],
        Field(
            description=(
                "The router configuration for this gateway. "
                "E.g. `{ type: sglang, policy: round_robin }`."
            ),
        ),
    ] = None
    domain: Annotated[
        Optional[str], Field(description="The gateway domain, e.g. `example.com`")
    ] = None
    public_ip: Annotated[bool, Field(description="Allocate public IP for the gateway")] = True
    certificate: Annotated[
        Optional[AnyGatewayCertificate],
        Field(
            description="The SSL certificate configuration."
            " Set to `null` to disable. Defaults to `type: lets-encrypt`"
        ),
    ] = LetsEncryptGatewayCertificate()
    tags: Annotated[
        Optional[Dict[str, str]],
        Field(
            description=(
                "The custom tags to associate with the gateway."
                " The tags are also propagated to the underlying backend resources."
                " If there is a conflict with backend-level tags, does not override them"
            )
        ),
    ] = None

    _validate_tags = validator("tags", pre=True, allow_reuse=True)(tags_validator)


class GatewaySpec(CoreModel):
    configuration: GatewayConfiguration
    configuration_path: Optional[str] = None


class Gateway(CoreModel):
    # TODO(0.21): Make `id` required.
    id: Optional[uuid.UUID] = None
    """`id` is only optional on the client side for compatibility with pre-0.20.7 servers."""
    name: str
    configuration: GatewayConfiguration
    created_at: datetime.datetime
    status: GatewayStatus
    status_message: Optional[str]
    hostname: Optional[str]
    """`hostname` is the IP address or hostname the user should set up the domain for.
    Could be the same as `ip_address` but also different, for example a gateway behind ALB.
    """
    ip_address: Optional[str]
    """`ip_address` is the IP address of the gateway instance."""
    instance_id: Optional[str]
    wildcard_domain: Optional[str]
    default: bool
    backend: Optional[BackendType] = None
    """`backend` duplicates a configuration field on the top level for backward compatibility
    with 0.19.x clients that expect it to be required.
    Remove after 0.21.
    """
    region: Optional[str] = None
    """`region` duplicates a configuration field on the top level for backward compatibility
    with 0.19.x clients that expect it to be required.
    Remove after 0.21.
    """


class GatewayPlan(CoreModel):
    project_name: str
    user: str
    spec: GatewaySpec
    current_resource: Optional[Gateway] = None


class GatewayComputeConfiguration(CoreModel):
    project_name: str
    instance_name: str
    backend: BackendType
    region: str
    instance_type: Optional[str] = None
    public_ip: bool
    ssh_key_pub: str
    certificate: Optional[AnyGatewayCertificate] = None
    tags: Optional[Dict[str, str]] = None
    router: Optional[AnyGatewayRouterConfig] = None


class GatewayProvisioningData(CoreModel):
    instance_id: str
    # TODO: rename `ip_address`; Kubernetes uses domain names here.
    ip_address: str
    region: str
    availability_zone: Optional[str] = None
    hostname: Optional[str] = None
    backend_data: Optional[str] = None
    """`backend_data` stores backend-specific data in JSON."""
