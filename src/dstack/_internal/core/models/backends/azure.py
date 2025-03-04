from typing import Dict

from pydantic import Field
from typing_extensions import Annotated, List, Literal, Optional, Union

from dstack._internal.core.models.common import CoreModel


class AzureConfigInfo(CoreModel):
    type: Literal["azure"] = "azure"
    tenant_id: str
    subscription_id: str
    resource_group: Optional[str] = None
    locations: Optional[List[str]] = None
    vpc_ids: Optional[Dict[str, str]] = None
    public_ips: Optional[bool] = None
    tags: Optional[Dict[str, str]] = None


class AzureClientCreds(CoreModel):
    type: Annotated[Literal["client"], Field(description="The type of credentials")] = "client"
    client_id: Annotated[str, Field(description="The client ID")]
    client_secret: Annotated[str, Field(description="The client secret")]
    # if tenant_id is missing, it will be populated from config info
    tenant_id: Optional[str]


class AzureDefaultCreds(CoreModel):
    type: Annotated[Literal["default"], Field(description="The type of credentials")] = "default"


AnyAzureCreds = Union[AzureClientCreds, AzureDefaultCreds]


class AzureCreds(CoreModel):
    __root__: AnyAzureCreds = Field(..., discriminator="type")


class AzureConfigInfoWithCreds(AzureConfigInfo):
    creds: AnyAzureCreds


AnyAzureConfigInfo = Union[AzureConfigInfo, AzureConfigInfoWithCreds]


class AzureStoredConfig(AzureConfigInfo):
    resource_group: str = ""
