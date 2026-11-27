from typing import Annotated, Literal

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class MassedComputeAPIKeyCreds(CoreModel):
    type: Annotated[Literal["api_key"], Field(description="The type of credentials")] = "api_key"
    api_key: Annotated[str, Field(description="The MassedCompute API key", min_length=1)]


AnyMassedComputeCreds = MassedComputeAPIKeyCreds
MassedComputeCreds = AnyMassedComputeCreds


class MassedComputeBackendConfig(CoreModel):
    type: Annotated[Literal["massedcompute"], Field(description="The type of backend")] = (
        "massedcompute"
    )


class MassedComputeBackendConfigWithCreds(MassedComputeBackendConfig):
    creds: Annotated[AnyMassedComputeCreds, Field(description="The credentials")]


class MassedComputeStoredConfig(MassedComputeBackendConfig):
    pass


class MassedComputeConfig(MassedComputeStoredConfig):
    creds: AnyMassedComputeCreds
