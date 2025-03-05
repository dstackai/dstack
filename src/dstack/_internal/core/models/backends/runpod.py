from typing import Annotated, List, Optional, Union

from pydantic import Field
from typing_extensions import Literal

from dstack._internal.core.models.common import CoreModel


class RunpodConfigInfo(CoreModel):
    type: Literal["runpod"] = "runpod"
    regions: Optional[List[str]] = None
    community_cloud: Optional[bool] = None


class RunpodAPIKeyCreds(CoreModel):
    type: Literal["api_key"] = "api_key"
    api_key: Annotated[str, Field(description="The API key")]


AnyRunpodCreds = RunpodAPIKeyCreds
RunpodCreds = AnyRunpodCreds


class RunpodConfigInfoWithCreds(RunpodConfigInfo):
    creds: AnyRunpodCreds


AnyRunpodConfigInfo = Union[RunpodConfigInfo, RunpodConfigInfoWithCreds]


class RunpodStoredConfig(RunpodConfigInfo):
    pass
