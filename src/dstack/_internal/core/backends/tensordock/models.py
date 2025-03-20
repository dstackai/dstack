from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class TensorDockAPIKeyCreds(CoreModel):
    type: Annotated[Literal["api_key"], Field(description="The type of credentials")] = "api_key"
    api_key: Annotated[str, Field(description="The API key")]
    api_token: Annotated[str, Field(description="The API token")]


AnyTensorDockCreds = TensorDockAPIKeyCreds
TensorDockCreds = AnyTensorDockCreds


class TensorDockBackendConfig(CoreModel):
    type: Annotated[Literal["tensordock"], Field(description="The type of backend")] = "tensordock"
    regions: Annotated[
        Optional[List[str]],
        Field(description="The list of TensorDock regions. Omit to use all regions"),
    ] = None


class TensorDockBackendConfigWithCreds(TensorDockBackendConfig):
    creds: Annotated[AnyTensorDockCreds, Field(description="The credentials")]


AnyTensorDockBackendConfig = Union[TensorDockBackendConfig, TensorDockBackendConfigWithCreds]


class TensorDockStoredConfig(TensorDockBackendConfig):
    pass


class TensorDockConfig(TensorDockStoredConfig):
    creds: AnyTensorDockCreds
