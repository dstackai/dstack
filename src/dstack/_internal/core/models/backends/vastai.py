from pydantic.fields import Field
from typing_extensions import Annotated, List, Literal, Optional, Union

from dstack._internal.core.models.common import CoreModel


class VastAIConfigInfo(CoreModel):
    type: Literal["vastai"] = "vastai"
    regions: Optional[List[str]] = None


class VastAIAPIKeyCreds(CoreModel):
    type: Annotated[Literal["api_key"], Field(description="The type of credentials")] = "api_key"
    api_key: Annotated[str, Field(description="The API key")]


AnyVastAICreds = VastAIAPIKeyCreds


VastAICreds = AnyVastAICreds


class VastAIConfigInfoWithCreds(VastAIConfigInfo):
    creds: AnyVastAICreds


AnyVastAIConfigInfo = Union[VastAIConfigInfo, VastAIConfigInfoWithCreds]


class VastAIStoredConfig(VastAIConfigInfo):
    pass
