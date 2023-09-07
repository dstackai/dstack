from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.users import User, UserWithCreds
from dstack._internal.server.db import get_session
from dstack._internal.server.models import UserModel
from dstack._internal.server.schemas.schemas import GetUserRequest
from dstack._internal.server.security.permissions import Authenticated
from dstack._internal.server.services import users
from dstack._internal.server.utils.routers import raise_not_found

router = APIRouter(prefix="/api/users", tags=["users"])


@router.post("/list")
async def list_users(
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
) -> List[User]:
    return await users.list_users(session=session)


@router.post("/get_my_user")
async def get_my_user(
    user: UserModel = Depends(Authenticated()),
) -> User:
    return users.user_model_to_user(user)


@router.post("/get_user")
async def get_user(
    body: GetUserRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
) -> UserWithCreds:
    res = await users.get_user_with_creds_by_name(session=session, username=body.username)
    if res is None:
        raise_not_found()
    return res


# async def create_user(
#     session: AsyncSession = Depends(get_session),
#     body: UserInfo,
#     user: User = Depends(GlobalAdmin())
# ):
#     pass


@router.post("/refresh-token")
async def refresh_token() -> UserWithCreds:
    pass
