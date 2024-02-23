from typing import List, Optional

from pydantic import BaseModel
from typing_extensions import Literal

from dstack._internal.core.models.backends.base import ConfigElement, ConfigMultiElement
from dstack._internal.core.models.common import ForbidExtra


class CudoComputeConfigInfo(BaseModel):
    type: Literal["cudocompute"] = "cudocompute"
    project_id: str
    regions: Optional[List[str]] = None


class CudoComputeStoredConfig(CudoComputeConfigInfo):
    pass


class CudoComputeAPIKeyCreds(ForbidExtra):
    type: Literal["api_key"] = "api_key"
    api_key: str


AnyCudoComputeCreds = CudoComputeAPIKeyCreds

CudoComputeCreds = AnyCudoComputeCreds


class CudoComputeConfigInfoWithCreds(CudoComputeConfigInfo):
    creds: AnyCudoComputeCreds


class CudoComputeConfigInfoWithCredsPartial(BaseModel):
    type: Literal["cudocompute"] = "cudocompute"
    creds: Optional[AnyCudoComputeCreds]
    project_id: Optional[str]
    regions: Optional[List[str]]


class CudoComputeConfigValues(BaseModel):
    type: Literal["cudocompute"] = "cudocompute"
    regions: Optional[ConfigMultiElement]
    project_id: Optional[ConfigElement]
