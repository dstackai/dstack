from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class SeewebAPITokenCreds(CoreModel):
    type: Annotated[Literal["api_token"], Field(description="The type of credentials")] = (
        "api_token"
    )
    api_token: Annotated[str, Field(description="The Seeweb ECS API token")]


AnySeewebCreds = SeewebAPITokenCreds
SeewebCreds = AnySeewebCreds


class SeewebBackendConfig(CoreModel):
    type: Annotated[Literal["seeweb"], Field(description="The type of backend")] = "seeweb"
    regions: Annotated[
        Optional[List[str]],
        Field(
            description="The list of Seeweb regions (e.g. it-mi2, it-fr2, ch-lug1, hr-zag1)."
            " Omit to use all regions"
        ),
    ] = None


class SeewebBackendConfigWithCreds(SeewebBackendConfig):
    creds: Annotated[AnySeewebCreds, Field(description="The credentials")]


AnySeewebBackendConfig = Union[SeewebBackendConfig, SeewebBackendConfigWithCreds]


class SeewebStoredConfig(SeewebBackendConfig):
    pass


class SeewebConfig(SeewebStoredConfig):
    creds: AnySeewebCreds
