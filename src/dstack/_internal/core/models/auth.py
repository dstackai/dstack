from typing import Annotated

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class OAuthProviderInfo(CoreModel):
    name: Annotated[str, Field(description="The OAuth2 provider name.")]
    enabled: Annotated[
        bool, Field(description="Whether the provider is configured on the server.")
    ]
