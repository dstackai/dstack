from pydantic.fields import Field
from typing_extensions import Annotated, List, Literal, Optional, Union

from dstack._internal.core.models.backends.base import ConfigMultiElement
from dstack._internal.core.models.common import CoreModel


class TensorDockConfigInfo(CoreModel):
    type: Literal["tensordock"] = "tensordock"
    regions: Optional[List[str]] = None


class TensorDockAPIKeyCreds(CoreModel):
    type: Annotated[Literal["api_key"], Field(description="The type of credentials")] = "api_key"
    api_key: Annotated[str, Field(description="The API key")]
    api_token: Annotated[str, Field(description="The API token")]


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
