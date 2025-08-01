from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class HotaisleAPIKeyCreds(CoreModel):
    type: Annotated[Literal["api_key"], Field(description="The type of credentials")] = "api_key"
    api_key: Annotated[str, Field(description="The Hotaisle API key")]


AnyHotaisleCreds = HotaisleAPIKeyCreds
HotaisleCreds = AnyHotaisleCreds


class HotaisleBackendConfig(CoreModel):
    type: Annotated[
        Literal["hotaisle"],
        Field(description="The type of backend"),
    ] = "hotaisle"
    team_handle: Annotated[str, Field(description="The Hotaisle team handle")]
    regions: Annotated[
        Optional[List[str]],
        Field(description="The list of Hotaisle regions. Omit to use all regions"),
    ] = None


class HotaisleBackendConfigWithCreds(HotaisleBackendConfig):
    creds: Annotated[AnyHotaisleCreds, Field(description="The credentials")]


AnyHotaisleBackendConfig = Union[HotaisleBackendConfig, HotaisleBackendConfigWithCreds]


class HotaisleBackendFileConfigWithCreds(HotaisleBackendConfig):
    creds: Annotated[AnyHotaisleCreds, Field(description="The credentials")]


class HotaisleStoredConfig(HotaisleBackendConfig):
    pass


class HotaisleConfig(HotaisleStoredConfig):
    creds: AnyHotaisleCreds
