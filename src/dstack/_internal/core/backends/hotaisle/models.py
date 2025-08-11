from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class HotAisleAPIKeyCreds(CoreModel):
    type: Annotated[Literal["api_key"], Field(description="The type of credentials")] = "api_key"
    api_key: Annotated[str, Field(description="The Hot Aisle API key")]


AnyHotAisleCreds = HotAisleAPIKeyCreds
HotAisleCreds = AnyHotAisleCreds


class HotAisleBackendConfig(CoreModel):
    type: Annotated[
        Literal["hotaisle"],
        Field(description="The type of backend"),
    ] = "hotaisle"
    team_handle: Annotated[str, Field(description="The Hot Aisle team handle")]
    regions: Annotated[
        Optional[List[str]],
        Field(description="The list of Hot Aisle regions. Omit to use all regions"),
    ] = None


class HotAisleBackendConfigWithCreds(HotAisleBackendConfig):
    creds: Annotated[AnyHotAisleCreds, Field(description="The credentials")]


AnyHotAisleBackendConfig = Union[HotAisleBackendConfig, HotAisleBackendConfigWithCreds]


class HotAisleBackendFileConfigWithCreds(HotAisleBackendConfig):
    creds: Annotated[AnyHotAisleCreds, Field(description="The credentials")]


class HotAisleStoredConfig(HotAisleBackendConfig):
    pass


class HotAisleConfig(HotAisleStoredConfig):
    creds: AnyHotAisleCreds
