from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class RunpodAPIKeyCreds(CoreModel):
    type: Literal["api_key"] = "api_key"
    api_key: Annotated[str, Field(description="The API key")]


AnyRunpodCreds = RunpodAPIKeyCreds
RunpodCreds = AnyRunpodCreds


class RunpodBackendConfig(CoreModel):
    type: Literal["runpod"] = "runpod"
    regions: Annotated[
        Optional[List[str]],
        Field(description="The list of Runpod regions. Omit to use all regions"),
    ] = None
    community_cloud: Annotated[
        Optional[bool],
        Field(
            description=(
                "Deprecated and ignored since 0.22.10."
                " Only Secure Cloud offers are suggested."
                " Will be removed in future versions"
            )
        ),
    ] = None
    """`community_cloud` is kept so that existing configs that set it still load."""


class RunpodBackendConfigWithCreds(RunpodBackendConfig):
    creds: Annotated[AnyRunpodCreds, Field(description="The credentials")]


AnyRunpodBackendConfig = Union[RunpodBackendConfig, RunpodBackendConfigWithCreds]


class RunpodStoredConfig(RunpodBackendConfig):
    pass


class RunpodConfig(RunpodStoredConfig):
    creds: AnyRunpodCreds
