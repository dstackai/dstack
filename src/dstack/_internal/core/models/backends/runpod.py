from typing import List, Optional

from pydantic import BaseModel
from typing_extensions import Literal

from dstack._internal.core.models.backends.base import ConfigMultiElement
from dstack._internal.core.models.common import ForbidExtra


class RunpodConfigInfo(BaseModel):
    type: Literal["runpod"] = "runpod"
    regions: Optional[List[str]] = None


class RunpodStoredConfig(RunpodConfigInfo):
    pass


class RunpodAPIKeyCreds(ForbidExtra):
    type: Literal["api_key"] = "api_key"
    api_key: str


AnyRunpodCreds = RunpodAPIKeyCreds
RunpodCreds = AnyRunpodCreds


class RunpodConfigInfoWithCreds(RunpodConfigInfo):
    creds: AnyRunpodCreds


class RunpodConfigInfoWithCredsPartial(BaseModel):
    type: Literal["runpod"] = "runpod"
    creds: Optional[AnyRunpodCreds]
    regions: Optional[List[str]]


class RunpodConfigValues(BaseModel):
    type: Literal["runpod"] = "runpod"
    regions: Optional[ConfigMultiElement]
