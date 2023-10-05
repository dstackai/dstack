from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.users import User, UserWithCreds
from dstack._internal.server.db import get_session
from dstack._internal.server.models import UserModel
from dstack._internal.server.schemas.users import (
    CreateUserRequest,
    GetUserRequest,
    RefreshTokenRequest,
    UpdateUserRequest,
)
from dstack._internal.server.security.permissions import Authenticated, GlobalAdmin
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
    res = await users.get_user_with_creds_by_name(
        session=session, current_user=user, username=body.username
    )
    if res is None:
        raise_not_found()
    return res


@router.post("/create")
async def create_user(
    body: CreateUserRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(GlobalAdmin()),
) -> User:
    res = await users.create_user(
        session=session, username=body.username, global_role=body.global_role
    )
    return users.user_model_to_user(res)


@router.post("/update")
async def update_user(
    body: UpdateUserRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(GlobalAdmin()),
) -> User:
    res = await users.update_user_role(
        session=session, username=body.username, global_role=body.global_role
    )
    return users.user_model_to_user(res)


@router.post("/refresh_token")
async def refresh_token(
    body: RefreshTokenRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(GlobalAdmin()),
) -> UserWithCreds:
    res = await users.refresh_user_token(session=session, username=body.username)
    return users.user_model_to_user_with_creds(res)
