import re
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from dstack._internal.hub.db.models import User
from dstack._internal.hub.models import DeleteUsers, UserInfo, UserInfoWithToken, UserPatch
from dstack._internal.hub.repository.users import UserManager
from dstack._internal.hub.routers.util import error_detail
from dstack._internal.hub.security.permissions import Authenticated, GlobalAdmin, raise_forbidden
from dstack._internal.hub.security.utils import ROLE_ADMIN

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/list")
async def list_users(user: User = Depends(Authenticated())) -> List[UserInfo]:
    users = await UserManager.get_user_list()
    project_users = []
    for u in users:
        if user.global_role == ROLE_ADMIN or user.name == u.name:
            project_user = UserInfo(
                user_name=u.name,
                global_role=u.global_role,
            )
            project_users.append(project_user)
    return project_users


@router.post("")
async def create_user(body: UserInfo, user: User = Depends(GlobalAdmin())) -> UserInfoWithToken:
    if not re.match(r"^[a-zA-Z0-9]([_-](?![_-])|[a-zA-Z0-9]){1,18}[a-zA-Z0-9]$", body.user_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=error_detail("Username is incorrect")
        )
    user = await UserManager.get_user_by_name(name=body.user_name)
    if user is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=error_detail("User exists")
        )
    user = await UserManager.create(name=body.user_name, global_role=body.global_role)
    return UserInfoWithToken(
        user_name=user.name,
        token=user.token,
        global_role=user.global_role,
    )


@router.delete("")
async def delete_users(body: DeleteUsers, user: User = Depends(GlobalAdmin())):
    for user_name in body.users:
        user = await _get_user(user_name)
        await UserManager.remove(user)


@router.get("/info")
async def get_my_user_info(user: User = Depends(Authenticated())) -> UserInfo:
    return UserInfo(user_name=user.name, global_role=user.global_role)


@router.post("/{user_name}/refresh-token")
async def refresh_token(
    user_name: str, user: User = Depends(Authenticated())
) -> UserInfoWithToken:
    user = await _get_user(user_name)
    user.token = str(uuid.uuid4())
    await UserManager.save(user)
    return UserInfoWithToken(
        user_name=user.name,
        token=user.token,
        global_role=user.global_role,
    )


@router.patch("/{user_name}")
async def update_user(
    user_name: str, body: UserPatch, user: User = Depends(GlobalAdmin())
) -> UserInfoWithToken:
    user = await _get_user(user_name)
    await UserManager.save(user)
    return UserInfoWithToken(
        user_name=user.name,
        token=user.token,
        global_role=body.global_role,
    )


@router.get("/{user_name}")
async def get_user(user_name: str, user: User = Depends(Authenticated())) -> UserInfoWithToken:
    if user.global_role != ROLE_ADMIN and user.name != user_name:
        raise_forbidden()
    user_to_get = await UserManager.get_user_by_name(name=user_name)
    return UserInfoWithToken(
        user_name=user_to_get.name,
        token=user_to_get.token,
        global_role=user_to_get.global_role,
    )


async def _get_user(user_name: str) -> User:
    user = await UserManager.get_user_by_name(name=user_name)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=error_detail("User does not exist")
        )
    return user
