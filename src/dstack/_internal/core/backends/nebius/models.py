from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field, root_validator

from dstack._internal.core.backends.base.models import fill_data
from dstack._internal.core.models.common import CoreModel


class NebiusServiceAccountCreds(CoreModel):
    type: Annotated[Literal["service_account"], Field(description="The type of credentials")] = (
        "service_account"
    )
    filename: Annotated[str, Field(description="The path to the service account file")]
    data: Annotated[str, Field(description="The contents of the service account file")]


AnyNebiusCreds = NebiusServiceAccountCreds
NebiusCreds = AnyNebiusCreds


class NebiusBackendConfig(CoreModel):
    type: Literal["nebius"] = "nebius"
    cloud_id: str
    folder_id: str
    network_id: str
    regions: Optional[List[str]] = None


class NebiusBackendConfigWithCreds(NebiusBackendConfig):
    creds: AnyNebiusCreds


AnyNebiusBackendConfig = Union[NebiusBackendConfig, NebiusBackendConfigWithCreds]


class NebiusServiceAccountFileCreds(CoreModel):
    type: Annotated[Literal["service_account"], Field(description="The type of credentials")] = (
        "service_account"
    )
    filename: Annotated[str, Field(description="The path to the service account file")]
    data: Annotated[
        Optional[str], Field(description="The contents of the service account file")
    ] = None

    @root_validator
    def fill_data(cls, values):
        return fill_data(values)


class NebiusBackendFileConfigWithCreds(NebiusBackendConfig):
    creds: NebiusServiceAccountFileCreds


class NebiusStoredConfig(NebiusBackendConfig):
    pass
