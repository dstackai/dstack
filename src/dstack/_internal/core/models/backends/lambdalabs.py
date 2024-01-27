from typing import List, Optional, Union

from pydantic import BaseModel
from typing_extensions import Literal

from dstack._internal.core.models.backends.base import ConfigMultiElement
from dstack._internal.core.models.common import ForbidExtra


class LambdaConfigInfo(BaseModel):
    type: Literal["lambda"] = "lambda"
    regions: Optional[List[str]] = None


class LambdaAPIKeyCreds(ForbidExtra):
    type: Literal["api_key"] = "api_key"
    api_key: str


AnyLambdaCreds = LambdaAPIKeyCreds


LambdaCreds = AnyLambdaCreds


class LambdaConfigInfoWithCreds(LambdaConfigInfo):
    creds: AnyLambdaCreds


AnyLambdaConfigInfo = Union[LambdaConfigInfo, LambdaConfigInfoWithCreds]


class LambdaConfigInfoWithCredsPartial(BaseModel):
    type: Literal["lambda"] = "lambda"
    creds: Optional[AnyLambdaCreds]
    regions: Optional[List[str]]


class LambdaConfigValues(BaseModel):
    type: Literal["lambda"] = "lambda"
    regions: Optional[ConfigMultiElement]


class LambdaStoredConfig(LambdaConfigInfo):
    pass
