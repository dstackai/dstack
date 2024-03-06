from typing import List, Optional, Union

from typing_extensions import Literal

from dstack._internal.core.models.backends.base import ConfigMultiElement
from dstack._internal.core.models.common import CoreModel


class LambdaConfigInfo(CoreModel):
    type: Literal["lambda"] = "lambda"
    regions: Optional[List[str]] = None


class LambdaAPIKeyCreds(CoreModel):
    type: Literal["api_key"] = "api_key"
    api_key: str


AnyLambdaCreds = LambdaAPIKeyCreds


LambdaCreds = AnyLambdaCreds


class LambdaConfigInfoWithCreds(LambdaConfigInfo):
    creds: AnyLambdaCreds


AnyLambdaConfigInfo = Union[LambdaConfigInfo, LambdaConfigInfoWithCreds]


class LambdaConfigInfoWithCredsPartial(CoreModel):
    type: Literal["lambda"] = "lambda"
    creds: Optional[AnyLambdaCreds]
    regions: Optional[List[str]]


class LambdaConfigValues(CoreModel):
    type: Literal["lambda"] = "lambda"
    regions: Optional[ConfigMultiElement]


class LambdaStoredConfig(LambdaConfigInfo):
    pass
