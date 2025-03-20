from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field

from dstack._internal.core.models.common import CoreModel

RUNPOD_COMMUNITY_CLOUD_DEFAULT = True


class RunpodAPIKeyCreds(CoreModel):
    type: Literal["api_key"] = "api_key"
    api_key: Annotated[str, Field(description="The API key")]


AnyRunpodCreds = RunpodAPIKeyCreds
RunpodCreds = AnyRunpodCreds


class RunpodBackendConfig(CoreModel):
    type: Literal["runpod"] = "runpod"
    regions: Annotated[
        Optional[List[str]],
        Field(description="The list of RunPod regions. Omit to use all regions"),
    ] = None
    community_cloud: Annotated[
        Optional[bool],
        Field(
            description=(
                "Whether Community Cloud offers can be suggested in addition to Secure Cloud."
                f" Defaults to `{str(RUNPOD_COMMUNITY_CLOUD_DEFAULT).lower()}`"
            )
        ),
    ] = None


class RunpodBackendConfigWithCreds(RunpodBackendConfig):
    creds: Annotated[AnyRunpodCreds, Field(description="The credentials")]


AnyRunpodBackendConfig = Union[RunpodBackendConfig, RunpodBackendConfigWithCreds]


class RunpodStoredConfig(RunpodBackendConfig):
    pass


class RunpodConfig(RunpodStoredConfig):
    creds: AnyRunpodCreds

    @property
    def allow_community_cloud(self) -> bool:
        if self.community_cloud is not None:
            return self.community_cloud
        return RUNPOD_COMMUNITY_CLOUD_DEFAULT
