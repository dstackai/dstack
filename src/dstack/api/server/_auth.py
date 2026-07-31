from typing import Optional

from dstack._internal.core.models.auth import OAuthProviderInfo
from dstack._internal.core.models.common import validate_extra_ignore
from dstack._internal.core.models.users import UserWithCreds
from dstack._internal.server.schemas.auth import (
    OAuthAuthorizeRequest,
    OAuthAuthorizeResponse,
    OAuthCallbackRequest,
)
from dstack.api.server._group import APIClientGroup


class AuthAPIClient(APIClientGroup):
    def list_providers(self) -> list[OAuthProviderInfo]:
        resp = self._request("/api/auth/list_providers")
        return validate_extra_ignore(list[OAuthProviderInfo], resp.json())

    def authorize(self, provider: str, local_port: Optional[int] = None) -> OAuthAuthorizeResponse:
        body = OAuthAuthorizeRequest(local_port=local_port)
        resp = self._request(f"/api/auth/{provider}/authorize", body=body.model_dump_json())
        return validate_extra_ignore(OAuthAuthorizeResponse, resp.json())

    def callback(
        self, provider: str, code: str, state: str, base_url: Optional[str] = None
    ) -> UserWithCreds:
        body = OAuthCallbackRequest(code=code, state=state, base_url=base_url)
        resp = self._request(f"/api/auth/{provider}/callback", body=body.model_dump_json())
        return validate_extra_ignore(UserWithCreds, resp.json())
