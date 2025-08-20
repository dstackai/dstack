from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class DigitalOceanAPIKeyCreds(CoreModel):
    type: Annotated[Literal["api_key"], Field(description="The type of credentials")] = "api_key"
    api_key: Annotated[str, Field(description="The API key")]


AnyDigitalOceanCreds = DigitalOceanAPIKeyCreds
DigitalOceanCreds = AnyDigitalOceanCreds


class DigitalOceanBackendConfig(CoreModel):
    type: Annotated[
        Literal["digitalocean"],
        Field(description="The type of backend"),
    ] = "digitalocean"
    flavor: Annotated[
        Optional[Literal["standard", "amd"]],
        Field(
            description="The DigitalOcean cloud flavor. Either 'standard' or 'amd'. Defaults to 'standard'"
        ),
    ] = "standard"
    regions: Annotated[
        Optional[List[str]],
        Field(description="The list of DigitalOcean regions. Omit to use all regions"),
    ] = None


class DigitalOceanBackendConfigWithCreds(DigitalOceanBackendConfig):
    creds: Annotated[AnyDigitalOceanCreds, Field(description="The credentials")]


AnyDigitalOceanBackendConfig = Union[DigitalOceanBackendConfig, DigitalOceanBackendConfigWithCreds]


class DigitalOceanBackendFileConfigWithCreds(DigitalOceanBackendConfig):
    creds: Annotated[AnyDigitalOceanCreds, Field(description="The credentials")]


class DigitalOceanStoredConfig(DigitalOceanBackendConfig):
    pass


class DigitalOceanConfig(DigitalOceanStoredConfig):
    creds: AnyDigitalOceanCreds
