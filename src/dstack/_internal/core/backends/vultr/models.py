from typing import Annotated, List, Literal, Optional

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class VultrAPIKeyCreds(CoreModel):
    type: Annotated[Literal["api_key"], Field(description="The type of credentials")] = "api_key"
    api_key: Annotated[str, Field(description="The API key")]


AnyVultrCreds = VultrAPIKeyCreds
VultrCreds = AnyVultrCreds


class VultrBackendConfig(CoreModel):
    type: Annotated[Literal["vultr"], Field(description="The type of backend")] = "vultr"
    regions: Annotated[
        Optional[List[str]],
        Field(description="The list of Vultr regions. Omit to use all regions"),
    ] = None


class VultrBackendConfigWithCreds(VultrBackendConfig):
    creds: Annotated[AnyVultrCreds, Field(description="The credentials")]


class VultrStoredConfig(VultrBackendConfig):
    pass


class VultrConfig(VultrStoredConfig):
    creds: AnyVultrCreds
