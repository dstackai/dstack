from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class JarvisLabsAPIKeyCreds(CoreModel):
    type: Annotated[Literal["api_key"], Field(description="The type of credentials")] = "api_key"
    api_key: Annotated[str, Field(description="The JarvisLabs API key")]


AnyJarvisLabsCreds = JarvisLabsAPIKeyCreds
JarvisLabsCreds = AnyJarvisLabsCreds


class JarvisLabsBackendConfig(CoreModel):
    type: Annotated[
        Literal["jarvislabs"],
        Field(description="The type of backend"),
    ] = "jarvislabs"
    regions: Annotated[
        Optional[List[str]],
        Field(description="The list of JarvisLabs regions. Omit to use all regions"),
    ] = None


class JarvisLabsBackendConfigWithCreds(JarvisLabsBackendConfig):
    creds: Annotated[AnyJarvisLabsCreds, Field(description="The credentials")]


AnyJarvisLabsBackendConfig = Union[
    JarvisLabsBackendConfig,
    JarvisLabsBackendConfigWithCreds,
]


class JarvisLabsBackendFileConfigWithCreds(JarvisLabsBackendConfig):
    creds: Annotated[AnyJarvisLabsCreds, Field(description="The credentials")]


class JarvisLabsStoredConfig(JarvisLabsBackendConfig):
    pass


class JarvisLabsConfig(JarvisLabsStoredConfig):
    creds: AnyJarvisLabsCreds
