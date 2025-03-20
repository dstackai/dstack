from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class DataCrunchAPIKeyCreds(CoreModel):
    type: Annotated[Literal["api_key"], Field(description="The type of credentials")] = "api_key"
    client_id: Annotated[str, Field(description="The client ID")]
    client_secret: Annotated[str, Field(description="The client secret")]


AnyDataCrunchCreds = DataCrunchAPIKeyCreds
DataCrunchCreds = AnyDataCrunchCreds


class DataCrunchBackendConfig(CoreModel):
    type: Annotated[Literal["datacrunch"], Field(description="The type of backend")] = "datacrunch"
    regions: Annotated[
        Optional[List[str]],
        Field(description="The list of DataCrunch regions. Omit to use all regions"),
    ] = None


class DataCrunchBackendConfigWithCreds(DataCrunchBackendConfig):
    creds: Annotated[AnyDataCrunchCreds, Field(description="The credentials")]


AnyDataCrunchBackendConfig = Union[DataCrunchBackendConfig, DataCrunchBackendConfigWithCreds]


class DataCrunchStoredConfig(DataCrunchBackendConfig):
    pass


class DataCrunchConfig(DataCrunchStoredConfig):
    creds: AnyDataCrunchCreds
