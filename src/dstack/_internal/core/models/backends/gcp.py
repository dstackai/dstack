from typing import List, Optional, Union

from pydantic import Field
from typing_extensions import Literal

from dstack._internal.core.models.backends.base import ConfigElement, ConfigMultiElement
from dstack._internal.core.models.common import CoreModel


class GCPConfigInfo(CoreModel):
    type: Literal["gcp"] = "gcp"
    project_id: str
    regions: Optional[List[str]] = None
    vpc_name: Optional[str] = None
    vpc_project_id: Optional[str] = None
    public_ips: Optional[bool] = None


class GCPServiceAccountCreds(CoreModel):
    type: Literal["service_account"] = "service_account"
    filename: str
    data: str


class GCPDefaultCreds(CoreModel):
    type: Literal["default"] = "default"


AnyGCPCreds = Union[GCPServiceAccountCreds, GCPDefaultCreds]


class GCPCreds(CoreModel):
    __root__: AnyGCPCreds = Field(..., discriminator="type")


class GCPConfigInfoWithCreds(GCPConfigInfo):
    creds: AnyGCPCreds


AnyGCPConfigInfo = Union[GCPConfigInfo, GCPConfigInfoWithCreds]


class GCPConfigInfoWithCredsPartial(CoreModel):
    type: Literal["gcp"] = "gcp"
    creds: Optional[AnyGCPCreds]
    project_id: Optional[str]
    regions: Optional[List[str]]
    vpc_name: Optional[str] = None
    vpc_project_id: Optional[str] = None
    public_ips: Optional[bool]


class GCPConfigValues(CoreModel):
    type: Literal["gcp"] = "gcp"
    default_creds: bool = False
    project_id: Optional[ConfigElement]
    regions: Optional[ConfigMultiElement]


class GCPStoredConfig(GCPConfigInfo):
    pass
