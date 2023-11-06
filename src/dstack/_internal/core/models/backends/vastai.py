from typing import List, Optional, Union

from pydantic import BaseModel
from typing_extensions import Literal

from dstack._internal.core.models.backends.base import ConfigMultiElement
from dstack._internal.core.models.common import ForbidExtra


class VastAIConfigInfo(BaseModel):
    type: Literal["vastai"] = "vastai"
    regions: Optional[List[str]] = None


class VastAIAPIKeyCreds(ForbidExtra):
    type: Literal["api_key"] = "api_key"
    api_key: str


AnyVastAICreds = VastAIAPIKeyCreds


VastAICreds = AnyVastAICreds


class VastAIConfigInfoWithCreds(VastAIConfigInfo):
    creds: AnyVastAICreds


AnyVastAIConfigInfo = Union[VastAIConfigInfo, VastAIConfigInfoWithCreds]


class VastAIConfigInfoWithCredsPartial(BaseModel):
    type: Literal["vastai"] = "vastai"
    creds: Optional[AnyVastAICreds]
    regions: Optional[List[str]]


class VastAIConfigValues(BaseModel):
    type: Literal["vastai"] = "vastai"
    regions: Optional[ConfigMultiElement]


class VastAIStoredConfig(VastAIConfigInfo):
    pass
