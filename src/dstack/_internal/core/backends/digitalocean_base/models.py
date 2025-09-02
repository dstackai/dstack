from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class BaseDigitalOceanAPIKeyCreds(CoreModel):
    type: Annotated[Literal["api_key"], Field(description="The type of credentials")] = "api_key"
    api_key: Annotated[str, Field(description="The API key")]


AnyBaseDigitalOceanCreds = BaseDigitalOceanAPIKeyCreds
BaseDigitalOceanCreds = AnyBaseDigitalOceanCreds


class BaseDigitalOceanBackendConfig(CoreModel):
    type: Annotated[
        Literal["amddevcloud", "digitalocean"],
        Field(description="The type of backend"),
    ]
    project_name: Annotated[Optional[str], Field(description="The name of the project")] = None
    regions: Annotated[
        Optional[List[str]],
        Field(description="The list of regions. Omit to use all regions"),
    ] = None


class BaseDigitalOceanBackendConfigWithCreds(BaseDigitalOceanBackendConfig):
    creds: Annotated[AnyBaseDigitalOceanCreds, Field(description="The credentials")]


AnyBaseDigitalOceanBackendConfig = Union[
    BaseDigitalOceanBackendConfig, BaseDigitalOceanBackendConfigWithCreds
]


class BaseDigitalOceanStoredConfig(BaseDigitalOceanBackendConfig):
    pass


class BaseDigitalOceanConfig(BaseDigitalOceanStoredConfig):
    creds: AnyBaseDigitalOceanCreds
