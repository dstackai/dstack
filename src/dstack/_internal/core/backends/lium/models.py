from typing import Annotated, Literal, Optional, Union

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class LiumAPIKeyCreds(CoreModel):
    type: Annotated[Literal["api_key"], Field(description="The type of credentials")] = "api_key"
    api_key: Annotated[str, Field(description="The Lium API key", min_length=1)]


AnyLiumCreds = LiumAPIKeyCreds
LiumCreds = AnyLiumCreds


class LiumBackendConfig(CoreModel):
    type: Annotated[Literal["lium"], Field(description="The type of backend")] = "lium"
    regions: Annotated[
        Optional[list[str]],
        Field(
            description=(
                "The list of Lium regions, such as `us-ca` or `de-he`. Omit to use all regions"
            )
        ),
    ] = None


class LiumBackendConfigWithCreds(LiumBackendConfig):
    creds: Annotated[AnyLiumCreds, Field(description="The credentials")]


AnyLiumBackendConfig = Union[LiumBackendConfig, LiumBackendConfigWithCreds]


class LiumStoredConfig(LiumBackendConfig):
    pass


class LiumConfig(LiumStoredConfig):
    creds: AnyLiumCreds
