from typing import List, Optional, Union

from typing_extensions import Literal

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


class NebiusStoredConfig(NebiusConfigInfo):
    pass
