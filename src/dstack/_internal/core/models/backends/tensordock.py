from typing import List, Optional, Union

from pydantic import BaseModel
from typing_extensions import Literal

from dstack._internal.core.models.backends.base import ConfigMultiElement
from dstack._internal.core.models.common import ForbidExtra


class TensorDockConfigInfo(BaseModel):
    type: Literal["tensordock"] = "tensordock"
    regions: Optional[List[str]] = None


class TensorDockAPIKeyCreds(ForbidExtra):
    type: Literal["api_key"] = "api_key"
    api_key: str
    api_token: str


AnyTensorDockCreds = TensorDockAPIKeyCreds


TensorDockCreds = AnyTensorDockCreds


class TensorDockConfigInfoWithCreds(TensorDockConfigInfo):
    creds: AnyTensorDockCreds


AnyTensorDockConfigInfo = Union[TensorDockConfigInfo, TensorDockConfigInfoWithCreds]


class TensorDockConfigInfoWithCredsPartial(BaseModel):
    type: Literal["tensordock"] = "tensordock"
    creds: Optional[AnyTensorDockCreds]
    regions: Optional[List[str]]


class TensorDockConfigValues(BaseModel):
    type: Literal["tensordock"] = "tensordock"
    regions: Optional[ConfigMultiElement]


class TensorDockStoredConfig(TensorDockConfigInfo):
    pass
