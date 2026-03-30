from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.keys import PublicKeyInfo
from dstack._internal.server.db import get_session
from dstack._internal.server.models import UserModel
from dstack._internal.server.schemas.public_keys import (
    AddPublicKeyRequest,
    DeletePublicKeysRequest,
)
from dstack._internal.server.security.permissions import Authenticated
from dstack._internal.server.services import public_keys as public_keys_services
from dstack._internal.server.utils.routers import (
    CustomORJSONResponse,
    get_base_api_additional_responses,
)

router = APIRouter(
    prefix="/api/users/public_keys",
    tags=["user public keys"],
    responses=get_base_api_additional_responses(),
)


@router.post("/list", response_model=list[PublicKeyInfo])
async def list_user_public_keys(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[UserModel, Depends(Authenticated())],
):
    public_keys = await public_keys_services.list_user_public_keys(session=session, user=user)
    return CustomORJSONResponse(public_keys)


@router.post("/add", response_model=PublicKeyInfo)
async def add_user_public_key(
    body: AddPublicKeyRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[UserModel, Depends(Authenticated())],
):
    public_key = await public_keys_services.add_user_public_key(
        session=session, user=user, key=body.key, name=body.name
    )
    return CustomORJSONResponse(public_key)


@router.post("/delete")
async def delete_user_public_keys(
    body: DeletePublicKeysRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[UserModel, Depends(Authenticated())],
):
    await public_keys_services.delete_user_public_keys(session=session, user=user, ids=body.ids)
