from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class LambdaAPIKeyCreds(CoreModel):
    type: Annotated[Literal["api_key"], Field(description="The type of credentials")] = "api_key"
    api_key: Annotated[str, Field(description="The API key")]


AnyLambdaCreds = LambdaAPIKeyCreds
LambdaCreds = AnyLambdaCreds


class LambdaBackendConfig(CoreModel):
    type: Annotated[Literal["lambda"], Field(description="The type of backend")] = "lambda"
    regions: Annotated[
        Optional[List[str]],
        Field(description="The list of Lambda regions. Omit to use all regions"),
    ] = None


class LambdaBackendConfigWithCreds(LambdaBackendConfig):
    creds: Annotated[AnyLambdaCreds, Field(description="The credentials")]


AnyLambdaBackendConfig = Union[LambdaBackendConfig, LambdaBackendConfigWithCreds]


class LambdaStoredConfig(LambdaBackendConfig):
    pass


class LambdaConfig(LambdaStoredConfig):
    creds: AnyLambdaCreds
