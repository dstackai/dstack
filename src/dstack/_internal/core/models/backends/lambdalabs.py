from pydantic.fields import Field
from typing_extensions import Annotated, List, Literal, Optional, Union

from dstack._internal.core.models.backends.base import ConfigMultiElement
from dstack._internal.core.models.common import CoreModel


class LambdaConfigInfo(CoreModel):
    type: Literal["lambda"] = "lambda"
    regions: Optional[List[str]] = None


class LambdaAPIKeyCreds(CoreModel):
    type: Annotated[Literal["api_key"], Field(description="The type of credentials")] = "api_key"
    api_key: Annotated[str, Field(description="The API key")]


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
