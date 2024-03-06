from typing import List, Optional, Union

from typing_extensions import Literal

from dstack._internal.core.models.backends.base import ConfigMultiElement
from dstack._internal.core.models.common import CoreModel


class VastAIConfigInfo(CoreModel):
    type: Literal["vastai"] = "vastai"
    regions: Optional[List[str]] = None


class VastAIAPIKeyCreds(CoreModel):
    type: Literal["api_key"] = "api_key"
    api_key: str


AnyVastAICreds = VastAIAPIKeyCreds


VastAICreds = AnyVastAICreds


class VastAIConfigInfoWithCreds(VastAIConfigInfo):
    creds: AnyVastAICreds


AnyVastAIConfigInfo = Union[VastAIConfigInfo, VastAIConfigInfoWithCreds]


class VastAIConfigInfoWithCredsPartial(CoreModel):
    type: Literal["vastai"] = "vastai"
    creds: Optional[AnyVastAICreds]
    regions: Optional[List[str]]


class VastAIConfigValues(CoreModel):
    type: Literal["vastai"] = "vastai"
    regions: Optional[ConfigMultiElement]


class VastAIStoredConfig(VastAIConfigInfo):
    pass
