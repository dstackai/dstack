from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class CrusoeAccessKeyCreds(CoreModel):
    type: Annotated[Literal["access_key"], Field(description="The type of credentials")] = (
        "access_key"
    )
    access_key: Annotated[str, Field(description="The Crusoe API access key")]
    secret_key: Annotated[str, Field(description="The Crusoe API secret key")]


AnyCrusoeCreds = CrusoeAccessKeyCreds
CrusoeCreds = AnyCrusoeCreds


class CrusoeBackendConfig(CoreModel):
    type: Annotated[
        Literal["crusoe"],
        Field(description="The type of backend"),
    ] = "crusoe"
    project_id: Annotated[str, Field(description="The Crusoe project ID")]
    regions: Annotated[
        Optional[List[str]],
        Field(description="The list of allowed Crusoe regions. Omit to use all regions"),
    ] = None


class CrusoeBackendConfigWithCreds(CrusoeBackendConfig):
    creds: Annotated[AnyCrusoeCreds, Field(description="The credentials")]


AnyCrusoeBackendConfig = Union[CrusoeBackendConfig, CrusoeBackendConfigWithCreds]


class CrusoeBackendFileConfigWithCreds(CrusoeBackendConfig):
    creds: Annotated[AnyCrusoeCreds, Field(description="The credentials")]


class CrusoeStoredConfig(CrusoeBackendConfig):
    pass


class CrusoeConfig(CrusoeStoredConfig):
    creds: AnyCrusoeCreds
