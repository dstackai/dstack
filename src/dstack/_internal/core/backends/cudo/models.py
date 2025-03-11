from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class CudoAPIKeyCreds(CoreModel):
    type: Annotated[Literal["api_key"], Field(description="The type of credentials")] = "api_key"
    api_key: Annotated[str, Field(description="The API key")]


AnyCudoCreds = CudoAPIKeyCreds
CudoCreds = AnyCudoCreds


class CudoBackendConfig(CoreModel):
    type: Annotated[Literal["cudo"], Field(description="The type of backend")] = "cudo"
    regions: Annotated[
        Optional[List[str]], Field(description="The list of Cudo regions. Omit to use all regions")
    ] = None
    project_id: Annotated[str, Field(description="The project ID")]


class CudoBackendConfigWithCreds(CudoBackendConfig):
    creds: Annotated[AnyCudoCreds, Field(description="The credentials")]


AnyCudoBackendConfig = Union[CudoBackendConfig, CudoBackendConfigWithCreds]


class CudoStoredConfig(CudoBackendConfig):
    pass


class CudoConfig(CudoStoredConfig):
    creds: AnyCudoCreds
