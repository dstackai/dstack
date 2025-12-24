from fastapi import APIRouter

from dstack._internal.core.models.auth import OAuthProviderInfo
from dstack._internal.server.schemas.auth import (
    OAuthGetNextRedirectRequest,
    OAuthGetNextRedirectResponse,
)
from dstack._internal.server.services import auth as auth_services
from dstack._internal.server.utils.routers import CustomORJSONResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/list_providers", response_model=list[OAuthProviderInfo])
async def list_providers():
    """
    Returns OAuth2 providers registered on the server.
    """
    return CustomORJSONResponse(auth_services.list_providers())


@router.post("/get_next_redirect", response_model=OAuthGetNextRedirectResponse)
async def get_next_redirect(body: OAuthGetNextRedirectRequest):
    """
    A helper endpoint that returns the next redirect URL in case the state encodes it.
    Can be used by the UI after the redirect from the provider
    to determine if the user needs to be redirected further (CLI login)
    or the auth callback endpoint needs to be called directly (UI login).
    """
    return CustomORJSONResponse(
        OAuthGetNextRedirectResponse(
            redirect_url=auth_services.get_next_redirect_url(code=body.code, state=body.state)
        )
    )
