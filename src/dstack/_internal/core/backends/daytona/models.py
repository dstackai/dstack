from typing import Annotated, Literal, Optional, Union

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class DaytonaAPIKeyCreds(CoreModel):
    type: Annotated[Literal["api_key"], Field(description="The type of credentials")] = "api_key"
    api_key: Annotated[str, Field(description="The Daytona API key", min_length=1)]


AnyDaytonaCreds = DaytonaAPIKeyCreds
DaytonaCreds = AnyDaytonaCreds


class DaytonaBackendConfig(CoreModel):
    type: Annotated[Literal["daytona"], Field(description="The type of backend")] = "daytona"
    regions: Annotated[
        Optional[list[str]],
        Field(
            description=(
                "The list of Daytona regions. GPU sandboxes use `earth`; CPU sandboxes use "
                "shared regions such as `us` and `eu`. Omit to use all regions"
            )
        ),
    ] = None


class DaytonaBackendConfigWithCreds(DaytonaBackendConfig):
    creds: Annotated[AnyDaytonaCreds, Field(description="The credentials")]


AnyDaytonaBackendConfig = Union[DaytonaBackendConfig, DaytonaBackendConfigWithCreds]


class DaytonaStoredConfig(DaytonaBackendConfig):
    pass


class DaytonaConfig(DaytonaStoredConfig):
    creds: AnyDaytonaCreds
