from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class VerdaAPIKeyCreds(CoreModel):
    type: Annotated[Literal["api_key"], Field(description="The type of credentials")] = "api_key"
    client_id: Annotated[str, Field(description="The client ID")]
    client_secret: Annotated[str, Field(description="The client secret")]


AnyVerdaCreds = VerdaAPIKeyCreds
VerdaCreds = AnyVerdaCreds


class VerdaBackendConfig(CoreModel):
    type: Annotated[Literal["verda", "datacrunch"], Field(description="The type of backend")]
    regions: Annotated[
        Optional[List[str]],
        Field(description="The list of Verda regions. Omit to use all regions"),
    ] = None


class VerdaBackendConfigWithCreds(VerdaBackendConfig):
    creds: Annotated[AnyVerdaCreds, Field(description="The credentials")]


AnyVerdaBackendConfig = Union[VerdaBackendConfig, VerdaBackendConfigWithCreds]


class VerdaStoredConfig(VerdaBackendConfig):
    pass


class VerdaConfig(VerdaStoredConfig):
    creds: AnyVerdaCreds
