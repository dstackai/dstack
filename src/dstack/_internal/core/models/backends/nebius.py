from typing import List, Optional, Union

from typing_extensions import Literal

from dstack._internal.core.models.backends.base import ConfigElement, ConfigMultiElement
from dstack._internal.core.models.common import CoreModel


class NebiusConfigInfo(CoreModel):
    type: Literal["nebius"] = "nebius"
    cloud_id: str
    folder_id: str
    network_id: str
    regions: Optional[List[str]] = None


class NebiusServiceAccountCreds(CoreModel):
    type: Literal["service_account"] = "service_account"
    filename: str
    data: str


AnyNebiusCreds = NebiusServiceAccountCreds


NebiusCreds = AnyNebiusCreds


class NebiusConfigInfoWithCreds(NebiusConfigInfo):
    creds: AnyNebiusCreds


AnyNebiusConfigInfo = Union[NebiusConfigInfo, NebiusConfigInfoWithCreds]


class NebiusConfigInfoWithCredsPartial(CoreModel):
    type: Literal["nebius"] = "nebius"
    creds: Optional[AnyNebiusCreds]
    cloud_id: Optional[str]
    folder_id: Optional[str]
    network_id: Optional[str]
    regions: Optional[List[str]]


class NebiusConfigValues(CoreModel):
    type: Literal["nebius"] = "nebius"
    cloud_id: Optional[ConfigElement]
    folder_id: Optional[ConfigElement]
    network_id: Optional[ConfigElement]
    regions: Optional[ConfigMultiElement]


class NebiusStoredConfig(NebiusConfigInfo):
    pass
