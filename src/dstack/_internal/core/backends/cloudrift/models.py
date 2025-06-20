from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class CloudRiftAPIKeyCreds(CoreModel):
    type: Annotated[Literal["api_key"], Field(description="The type of credentials")] = "api_key"
    api_key: Annotated[str, Field(description="The API key")]


AnyCloudRiftCreds = CloudRiftAPIKeyCreds
CloudRiftCreds = AnyCloudRiftCreds


class CloudRiftBackendConfig(CoreModel):
    type: Annotated[
        Literal["cloudrift"],
        Field(description="The type of backend"),
    ] = "cloudrift"
    regions: Annotated[
        Optional[List[str]],
        Field(description="The list of CloudRift regions. Omit to use all regions"),
    ] = None


class CloudRiftBackendConfigWithCreds(CloudRiftBackendConfig):
    creds: Annotated[AnyCloudRiftCreds, Field(description="The credentials")]


AnyCloudRiftBackendConfig = Union[CloudRiftBackendConfig, CloudRiftBackendConfigWithCreds]


class CloudRiftStoredConfig(CloudRiftBackendConfig):
    pass


class CloudRiftConfig(CloudRiftStoredConfig):
    creds: AnyCloudRiftCreds
