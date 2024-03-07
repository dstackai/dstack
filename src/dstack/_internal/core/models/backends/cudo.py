from typing import List, Optional

from pydantic import BaseModel
from typing_extensions import Literal

from dstack._internal.core.models.backends.base import ConfigElement, ConfigMultiElement
from dstack._internal.core.models.common import ForbidExtra


class CudoConfigInfo(BaseModel):
    type: Literal["cudo"] = "cudo"
    project_id: str
    regions: Optional[List[str]] = None


class CudoStoredConfig(CudoConfigInfo):
    pass


class CudoAPIKeyCreds(ForbidExtra):
    type: Literal["api_key"] = "api_key"
    api_key: str


AnyCudoCreds = CudoAPIKeyCreds
CudoCreds = AnyCudoCreds


class CudoConfigInfoWithCreds(CudoConfigInfo):
    creds: AnyCudoCreds


class CudoConfigInfoWithCredsPartial(BaseModel):
    type: Literal["cudo"] = "cudo"
    creds: Optional[AnyCudoCreds]
    project_id: Optional[str]
    regions: Optional[List[str]]


class CudoConfigValues(BaseModel):
    type: Literal["cudo"] = "cudo"
    regions: Optional[ConfigMultiElement]
    project_id: Optional[ConfigElement]
