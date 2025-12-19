from typing import Annotated, Optional

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class OAuthProviderInfo(CoreModel):
    name: Annotated[str, Field(description="The OAuth2 provider name.")]
    enabled: Annotated[
        bool, Field(description="Whether the provider is configured on the server.")
    ]


class OAuthState(CoreModel):
    """
    A struct that the server puts in the OAuth2 state parameter.
    """

    value: Annotated[str, Field(description="A random string to protect against CSRF.")]
    local_port: Annotated[
        Optional[int],
        Field(
            description="If specified, the user is redirected to localhost:local_port after the redirect from the provider.",
            ge=1,
            le=65535,
        ),
    ] = None
