import re
import uuid
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer
from fastapi.security.http import HTTPAuthorizationCredentials

from dstack.hub.models import DeleteUsers, ProjectDelete, User, UserInfo, UserPatch
from dstack.hub.repository.role import RoleManager
from dstack.hub.repository.user import UserManager
from dstack.hub.security.scope import Scope

router = APIRouter(prefix="/api/users", tags=["users"])

security = HTTPBearer()


@router.post("", response_model=User, dependencies=[Depends(Scope("users:info:read"))])
async def users_create(body: User) -> User:
    if not re.match(r"^[a-zA-Z0-9]([_-](?![_-])|[a-zA-Z0-9]){1,18}[a-zA-Z0-9]$", body.user_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Username is incorrect"
        )
    user = await UserManager.get_user_by_name(name=body.user_name)
    if user is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User exists")
    user = await UserManager.create(name=body.user_name, role=body.global_role)
    return User(
        user_name=user.name,
        token=user.token,
        global_role=user.project_role.name,
    )


@router.delete("", dependencies=[Depends(Scope("users:get:read"))])
async def users_delete(body: DeleteUsers):
    for user_name in body.users:
        user = await UserManager.get_user_by_name(name=user_name)
        if user is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not exists")
        await UserManager.remove(user)


@router.get("/info", response_model=UserInfo, dependencies=[Depends(Scope("users:info:read"))])
async def users_info(authorization: HTTPAuthorizationCredentials = Depends(security)) -> UserInfo:
    user = await UserManager.get_user_by_token(authorization.credentials)
    return UserInfo(user_name=user.name, global_role=user.project_role.name)


@router.get("/list", response_model=List[User], dependencies=[Depends(Scope("users:list:read"))])
async def users_list() -> List[User]:
    users = await UserManager.get_user_list()
    project_users = []
    for user in users:
        project_user = User(
            user_name=user.name,
            token=user.token,
            global_role=user.project_role.name,
        )
        project_users.append(project_user)
    return project_users


@router.post(
    "/{user_name}/refresh-token",
    response_model=User,
    dependencies=[Depends(Scope("users:refresh:write"))],
)
async def users_get(user_name: str) -> User:
    user = await UserManager.get_user_by_name(name=user_name)
    user.token = str(uuid.uuid4())
    await UserManager.save(user)
    return User(
        user_name=user.name,
        token=user.token,
        global_role=user.project_role.name,
    )


@router.patch("/{user_name}", response_model=User, dependencies=[Depends(Scope("users:get:read"))])
async def users_patch(user_name: str, body: UserPatch) -> User:
    user = await UserManager.get_user_by_name(name=user_name)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not exists")
    role = await RoleManager.get_by_name(name=body.global_role)
    if role is None:
        role = await RoleManager.create(name=body.global_role)  # TODO Replace with Exception
    user.role_id = role.id
    await UserManager.save(user)
    return User(
        user_name=user.name,
        token=user.token,
        global_role=user.project_role.name,
    )


@router.get("/{user_name}", response_model=User, dependencies=[Depends(Scope("users:get:read"))])
async def users_get(user_name: str) -> User:
    user = await UserManager.get_user_by_name(name=user_name)
    return User(
        user_name=user.name,
        token=user.token,
        global_role=user.project_role.name,
    )
