import secrets
import urllib.parse
from base64 import b64decode, b64encode
from typing import Optional

from fastapi import Request, Response

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.auth import OAuthProviderInfo, OAuthState
from dstack._internal.server import settings
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


_OAUTH_STATE_COOKIE_KEY = "oauth-state"

_OAUTH_PROVIDERS: list[OAuthProviderInfo] = []


def register_provider(provider_info: OAuthProviderInfo):
    """
    Registers an OAuth2 provider supported on the server.
    If the provider is supported but not configured, it should be registered with `enabled=False`.
    The provider must register endpoints `/api/auth/{provider}/authorize` and `/api/auth/{provider}/callback`
    as defined by the client (see `dstack.api.server._auth.AuthAPIClient`).
    """
    _OAUTH_PROVIDERS.append(provider_info)


def list_providers() -> list[OAuthProviderInfo]:
    return _OAUTH_PROVIDERS


def generate_oauth_state(local_port: Optional[int] = None) -> str:
    value = str(secrets.token_hex(16))
    state = OAuthState(value=value, local_port=local_port)
    return b64encode(state.json().encode()).decode()


def set_state_cookie(response: Response, state: str):
    response.set_cookie(
        key=_OAUTH_STATE_COOKIE_KEY,
        value=state,
        secure=settings.SERVER_URL.startswith("https://"),
        samesite="strict",
        httponly=True,
    )


def get_validated_state(request: Request, state: str) -> OAuthState:
    state_cookie = request.cookies.get(_OAUTH_STATE_COOKIE_KEY)
    if state != state_cookie:
        raise ServerClientError("Invalid state token")
    decoded_state = _decode_state(state)
    if decoded_state is None:
        raise ServerClientError("Invalid state token")
    return decoded_state


def get_next_redirect_url(code: str, state: str) -> Optional[str]:
    decoded_state = _decode_state(state)
    if decoded_state is None:
        raise ServerClientError("Invalid state token")
    if decoded_state.local_port is None:
        return None
    params = {"code": code, "state": state}
    redirect_url = f"http://localhost:{decoded_state.local_port}/auth/callback?{urllib.parse.urlencode(params)}"
    return redirect_url


def _decode_state(state: str) -> Optional[OAuthState]:
    try:
        return OAuthState.parse_raw(b64decode(state, validate=True).decode())
    except Exception as e:
        logger.debug("Exception when decoding OAuth2 state parameter: %s", repr(e))
        return None
