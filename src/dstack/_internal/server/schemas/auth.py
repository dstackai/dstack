from typing import Annotated, Optional

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class OAuthInfoResponse(CoreModel):
    enabled: Annotated[
        bool, Field(description="Whether the OAuth2 provider is configured on the server.")
    ]


class OAuthAuthorizeRequest(CoreModel):
    base_url: Annotated[
        Optional[str],
        Field(
            description=(
                "The server base URL used to access the dstack server, e.g. `http://localhost:3000`."
                " Used to build redirect URLs when the dstack server is available on multiple domains."
            )
        ),
    ] = None


class OAuthAuthorizeResponse(CoreModel):
    authorization_url: Annotated[str, Field(description="An OAuth2 authorization URL.")]


class OAuthCallbackRequest(CoreModel):
    code: Annotated[
        str,
        Field(
            description="The OAuth2 authorization code received from the provider in the redirect URL."
        ),
    ]
    state: Annotated[
        str,
        Field(description="The state parameter received from the provider in the redirect URL."),
    ]
    base_url: Annotated[
        Optional[str],
        Field(
            description=(
                "The server base URL used to access the dstack server, e.g. `http://localhost:3000`."
                " Used to build redirect URLs when the dstack server is available on multiple domains."
                " It must match the base URL specified when generating the authorization URL."
            )
        ),
    ] = None
