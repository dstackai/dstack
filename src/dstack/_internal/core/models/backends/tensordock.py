from typing import List, Optional, Union

from typing_extensions import Literal

from dstack._internal.core.models.backends.base import ConfigMultiElement
from dstack._internal.core.models.common import CoreModel


class TensorDockConfigInfo(CoreModel):
    type: Literal["tensordock"] = "tensordock"
    regions: Optional[List[str]] = None


class TensorDockAPIKeyCreds(CoreModel):
    type: Literal["api_key"] = "api_key"
    api_key: str
    api_token: str


AnyTensorDockCreds = TensorDockAPIKeyCreds


TensorDockCreds = AnyTensorDockCreds


class TensorDockConfigInfoWithCreds(TensorDockConfigInfo):
    creds: AnyTensorDockCreds


AnyTensorDockConfigInfo = Union[TensorDockConfigInfo, TensorDockConfigInfoWithCreds]


class TensorDockConfigInfoWithCredsPartial(CoreModel):
    type: Literal["tensordock"] = "tensordock"
    creds: Optional[AnyTensorDockCreds]
    regions: Optional[List[str]]


class TensorDockConfigValues(CoreModel):
    type: Literal["tensordock"] = "tensordock"
    regions: Optional[ConfigMultiElement]


class TensorDockStoredConfig(TensorDockConfigInfo):
    pass
