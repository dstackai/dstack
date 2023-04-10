from typing import Tuple

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer
from fastapi.security.http import HTTPAuthorizationCredentials

from dstack.hub.db.models import Project, User
from dstack.hub.repository.projects import ProjectManager
from dstack.hub.repository.users import UserManager
from dstack.hub.routers.util import error_detail, get_project
from dstack.hub.security.utils import ROLE_ADMIN, ROLE_READ, ROLE_RUN


class Authenticated:
    async def __call__(self, token: HTTPAuthorizationCredentials = Security(HTTPBearer())):
        user = await _get_user(token.credentials)
        return user


class GlobalAdmin:
    async def __call__(self, token: HTTPAuthorizationCredentials = Security(HTTPBearer())) -> User:
        user = await _get_user(token.credentials)
        if user.global_role == ROLE_ADMIN:
            return user
        raise_forbidden()


class ProjectAdmin:
    async def __call__(
        self, project_name: str, token: HTTPAuthorizationCredentials = Security(HTTPBearer())
    ) -> Tuple[User, Project]:
        user = await _get_user(token.credentials)
        project = await get_project(project_name=project_name)
        await ensure_user_project_admin(user, project)
        return user, project


async def ensure_user_project_admin(user: User, project: Project):
    if user.global_role == ROLE_ADMIN:
        return
    member = await ProjectManager.get_member(user, project)
    if member is None or member.project_role != ROLE_ADMIN:
        raise_forbidden()


# In the current roles model every User has at least "read" global role,
# so every user has read access to every project.
class ProjectMember:
    async def __call__(
        self, project_name: str, token: HTTPAuthorizationCredentials = Security(HTTPBearer())
    ) -> Tuple[User, Project]:
        user = await _get_user(token.credentials)
        project = await get_project(project_name=project_name)
        return user, project


def raise_forbidden():
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=error_detail("Access denied"),
    )


async def _get_user(token: str) -> User:
    user = await UserManager.get_user_by_token(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail("Token is invalid"),
        )
    return user
