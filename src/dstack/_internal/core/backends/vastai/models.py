from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class VastAIAPIKeyCreds(CoreModel):
    type: Annotated[Literal["api_key"], Field(description="The type of credentials")] = "api_key"
    api_key: Annotated[str, Field(description="The API key")]


AnyVastAICreds = VastAIAPIKeyCreds
VastAICreds = AnyVastAICreds


class VastAIBackendConfig(CoreModel):
    type: Annotated[Literal["vastai"], Field(description="The type of backend")] = "vastai"
    regions: Annotated[
        Optional[List[str]],
        Field(description="The list of VastAI regions. Omit to use all regions"),
    ] = None


class VastAIBackendConfigWithCreds(VastAIBackendConfig):
    creds: Annotated[AnyVastAICreds, Field(description="The credentials")]


AnyVastAIBackendConfig = Union[VastAIBackendConfig, VastAIBackendConfigWithCreds]


class VastAIStoredConfig(VastAIBackendConfig):
    pass


class VastAIConfig(VastAIStoredConfig):
    creds: AnyVastAICreds
