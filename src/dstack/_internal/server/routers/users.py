from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.core.models.users import User, UsersInfoListOrUsersList, UserWithCreds
from dstack._internal.server.db import get_session
from dstack._internal.server.models import UserModel
from dstack._internal.server.schemas.users import (
    CreateUserRequest,
    DeleteUsersRequest,
    GetUserRequest,
    ListUsersRequest,
    RefreshTokenRequest,
    UpdateUserRequest,
)
from dstack._internal.server.security.permissions import Authenticated, GlobalAdmin
from dstack._internal.server.services import events, users
from dstack._internal.server.utils.routers import (
    CustomORJSONResponse,
    get_base_api_additional_responses,
)

router = APIRouter(
    prefix="/api/users",
    tags=["users"],
    responses=get_base_api_additional_responses(),
)


@router.post("/list", response_model=UsersInfoListOrUsersList)
async def list_users(
    body: Optional[ListUsersRequest] = None,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
):
    """
    Returns users visible to the user, sorted by descending `created_at`.

    Admins see all non-deleted users. Non-admins only see themselves.

    The results are paginated. To get the next page, pass `created_at` and `id` of
    the last user from the previous page as `prev_created_at` and `prev_id`.
    """
    if body is None:
        # For backward compatibility
        body = ListUsersRequest()
    return CustomORJSONResponse(
        await users.list_users_for_user(
            session=session,
            user=user,
            return_total_count=body.return_total_count,
            name_pattern=body.name_pattern,
            prev_created_at=body.prev_created_at,
            prev_id=body.prev_id,
            limit=body.limit,
            ascending=body.ascending,
        )
    )


@router.post("/get_my_user", response_model=UserWithCreds)
async def get_my_user(
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
):
    if user.ssh_private_key is None or user.ssh_public_key is None:
        # Generate keys for pre-0.19.33 users
        await users.refresh_ssh_key(session=session, actor=user)
    return CustomORJSONResponse(users.user_model_to_user_with_creds(user))


@router.post("/get_user", response_model=UserWithCreds)
async def get_user(
    body: GetUserRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
):
    res = await users.get_user_with_creds_by_name(
        session=session, current_user=user, username=body.username
    )
    if res is None:
        raise ResourceNotExistsError()
    return CustomORJSONResponse(res)


@router.post("/create", response_model=User)
async def create_user(
    body: CreateUserRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(GlobalAdmin()),
):
    res = await users.create_user(
        session=session,
        username=body.username,
        global_role=body.global_role,
        email=body.email,
        active=body.active,
        creator=user,
    )
    return CustomORJSONResponse(users.user_model_to_user(res))


@router.post("/update", response_model=User)
async def update_user(
    body: UpdateUserRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(GlobalAdmin()),
):
    res = await users.update_user(
        session=session,
        actor=events.UserActor.from_user(user),
        username=body.username,
        global_role=body.global_role,
        email=body.email,
        active=body.active,
    )
    if res is None:
        raise ResourceNotExistsError()
    return CustomORJSONResponse(users.user_model_to_user(res))


@router.post("/refresh_ssh_key", response_model=UserWithCreds)
async def refresh_ssh_key(
    body: RefreshTokenRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
):
    res = await users.refresh_ssh_key(session=session, actor=user, username=body.username)
    if res is None:
        raise ResourceNotExistsError()
    return CustomORJSONResponse(users.user_model_to_user_with_creds(res))


@router.post("/refresh_token", response_model=UserWithCreds)
async def refresh_token(
    body: RefreshTokenRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
):
    res = await users.refresh_user_token(session=session, actor=user, username=body.username)
    if res is None:
        raise ResourceNotExistsError()
    return CustomORJSONResponse(users.user_model_to_user_with_creds(res))


@router.post("/delete")
async def delete_users(
    body: DeleteUsersRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(GlobalAdmin()),
):
    await users.delete_users(
        session=session,
        actor=user,
        usernames=body.users,
    )
