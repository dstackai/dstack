from typing import Annotated

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class GetUpstreamRequest(CoreModel):
    # The format of id is intentionally not limited to UUID to allow further extensions
    id: str


class UpstreamHost(CoreModel):
    host: Annotated[str, Field(description="The hostname or IP address")]
    port: Annotated[int, Field(description="The SSH port")]
    user: Annotated[str, Field(description="The user to log in")]
    private_key: Annotated[str, Field(description="The private key in OpenSSH file format")]


class GetUpstreamResponse(CoreModel):
    hosts: Annotated[
        list[UpstreamHost],
        Field(description="The chain of SSH hosts, the jump host(s) first, the target host last"),
    ]
    authorized_keys: Annotated[
        list[str], Field(description="The list of authorized public keys in OpenSSH file format")
    ]
