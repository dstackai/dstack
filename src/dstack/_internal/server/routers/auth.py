from fastapi import APIRouter

from dstack._internal.core.models.auth import OAuthProviderInfo
from dstack._internal.server.services import auth as auth_services
from dstack._internal.server.utils.routers import CustomORJSONResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/list_providers", response_model=list[OAuthProviderInfo])
async def list_providers():
    """
    Returns OAuth2 providers registered on the server.
    """
    return CustomORJSONResponse(auth_services.list_providers())
