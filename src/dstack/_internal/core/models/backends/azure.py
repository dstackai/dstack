from typing import List, Optional, Union

from pydantic import BaseModel, Field
from typing_extensions import Literal

from dstack._internal.core.models.backends.base import ConfigElement, ConfigMultiElement
from dstack._internal.core.models.common import ForbidExtra


class AzureConfigInfo(BaseModel):
    type: Literal["azure"] = "azure"
    tenant_id: str
    subscription_id: str
    locations: Optional[List[str]] = None


class AzureClientCreds(ForbidExtra):
    type: Literal["client"] = "client"
    client_id: str
    client_secret: str
    # if tenant_id is missing, it will be populated from config info
    tenant_id: Optional[str]


class AzureDefaultCreds(ForbidExtra):
    type: Literal["default"] = "default"


AnyAzureCreds = Union[AzureClientCreds, AzureDefaultCreds]


class AzureCreds(BaseModel):
    __root__: AnyAzureCreds = Field(..., discriminator="type")


class AzureConfigInfoWithCreds(AzureConfigInfo):
    creds: AnyAzureCreds


AnyAzureConfigInfo = Union[AzureConfigInfo, AzureConfigInfoWithCreds]


class AzureConfigInfoWithCredsPartial(BaseModel):
    type: Literal["azure"] = "azure"
    creds: Optional[AnyAzureCreds]
    tenant_id: Optional[str]
    subscription_id: Optional[str]
    locations: Optional[List[str]]


class AzureConfigValues(BaseModel):
    type: Literal["azure"] = "azure"
    default_creds: bool = False
    tenant_id: Optional[ConfigElement]
    subscription_id: Optional[ConfigElement]
    locations: Optional[ConfigMultiElement]


class AzureStoredConfig(AzureConfigInfo):
    resource_group: str
