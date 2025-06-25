from typing import Annotated, Optional, Tuple

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPBearer
from fastapi.security.http import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.services.projects import (
    get_project_model_by_name,
    get_user_project_role,
)
from dstack._internal.server.services.users import log_in_with_token
from dstack._internal.server.utils.routers import (
    error_forbidden,
    error_invalid_token,
    error_not_found,
)


class Authenticated:
    async def __call__(
        self,
        session: AsyncSession = Depends(get_session),
        token: HTTPAuthorizationCredentials = Security(HTTPBearer()),
    ) -> UserModel:
        user = await log_in_with_token(session=session, token=token.credentials)
        if user is None:
            raise error_invalid_token()
        return user


class GlobalAdmin:
    async def __call__(
        self,
        session: AsyncSession = Depends(get_session),
        token: HTTPAuthorizationCredentials = Security(HTTPBearer()),
    ) -> UserModel:
        user = await log_in_with_token(session=session, token=token.credentials)
        if user is None:
            raise error_invalid_token()
        if user.global_role == GlobalRole.ADMIN:
            return user
        raise error_forbidden()


class ProjectAdmin:
    async def __call__(
        self,
        project_name: str,
        session: AsyncSession = Depends(get_session),
        token: HTTPAuthorizationCredentials = Security(HTTPBearer()),
    ) -> Tuple[UserModel, ProjectModel]:
        user = await log_in_with_token(session=session, token=token.credentials)
        if user is None:
            raise error_invalid_token()
        project = await get_project_model_by_name(session=session, project_name=project_name)
        if project is None:
            raise error_not_found()
        if user.global_role == GlobalRole.ADMIN:
            return user, project
        project_role = get_user_project_role(user=user, project=project)
        if project_role == ProjectRole.ADMIN:
            return user, project
        raise error_forbidden()


class ProjectManager:
    """
    Allows project admins and managers to manage projects.
    """

    async def __call__(
        self,
        project_name: str,
        session: AsyncSession = Depends(get_session),
        token: HTTPAuthorizationCredentials = Security(HTTPBearer()),
    ) -> Tuple[UserModel, ProjectModel]:
        user = await log_in_with_token(session=session, token=token.credentials)
        if user is None:
            raise error_invalid_token()
        project = await get_project_model_by_name(session=session, project_name=project_name)
        if project is None:
            raise error_not_found()

        if user.global_role == GlobalRole.ADMIN:
            return user, project

        project_role = get_user_project_role(user=user, project=project)
        if project_role in [ProjectRole.ADMIN, ProjectRole.MANAGER]:
            return user, project

        raise error_forbidden()


class ProjectMember:
    async def __call__(
        self,
        *,
        session: AsyncSession = Depends(get_session),
        project_name: str,
        token: HTTPAuthorizationCredentials = Security(HTTPBearer()),
    ) -> Tuple[UserModel, ProjectModel]:
        return await get_project_member(session, project_name, token.credentials)


class ProjectMemberOrPublicAccess:
    """
    Allows access to project for:
    - Global admins
    - Project members
    - Any authenticated user if the project is public
    """

    async def __call__(
        self,
        *,
        session: AsyncSession = Depends(get_session),
        project_name: str,
        token: HTTPAuthorizationCredentials = Security(HTTPBearer()),
    ) -> Tuple[UserModel, ProjectModel]:
        user = await log_in_with_token(session=session, token=token.credentials)
        if user is None:
            raise error_invalid_token()

        project = await get_project_model_by_name(session=session, project_name=project_name)
        if project is None:
            raise error_not_found()

        if user.global_role == GlobalRole.ADMIN:
            return user, project

        project_role = get_user_project_role(user=user, project=project)
        if project_role is not None:
            return user, project

        if project.is_public:
            return user, project

        raise error_forbidden()


class ProjectManagerOrPublicProject:
    """
    Allows:
    1. Project managers to perform member management operations
    2. Access to public projects for any authenticated user
    """

    def __init__(self):
        self.project_manager = ProjectManager()

    async def __call__(
        self,
        project_name: str,
        session: AsyncSession = Depends(get_session),
        token: HTTPAuthorizationCredentials = Security(HTTPBearer()),
    ) -> Tuple[UserModel, ProjectModel]:
        user = await log_in_with_token(session=session, token=token.credentials)
        if user is None:
            raise error_invalid_token()
        project = await get_project_model_by_name(session=session, project_name=project_name)
        if project is None:
            raise error_not_found()

        if user.global_role == GlobalRole.ADMIN:
            return user, project

        project_role = get_user_project_role(user=user, project=project)
        if project_role in [ProjectRole.ADMIN, ProjectRole.MANAGER]:
            return user, project

        if project.is_public:
            return user, project

        raise error_forbidden()


class ProjectManagerOrSelfLeave:
    """
    Allows:
    1. Project managers to remove any members
    2. Any project member to leave (remove themselves)
    """

    async def __call__(
        self,
        project_name: str,
        session: AsyncSession = Depends(get_session),
        token: HTTPAuthorizationCredentials = Security(HTTPBearer()),
    ) -> Tuple[UserModel, ProjectModel]:
        user = await log_in_with_token(session=session, token=token.credentials)
        if user is None:
            raise error_invalid_token()
        project = await get_project_model_by_name(session=session, project_name=project_name)
        if project is None:
            raise error_not_found()

        if user.global_role == GlobalRole.ADMIN:
            return user, project

        project_role = get_user_project_role(user=user, project=project)
        if project_role is not None:
            return user, project

        raise error_forbidden()


class OptionalServiceAccount:
    def __init__(self, token: Optional[str]) -> None:
        self._token = token

    async def __call__(
        self,
        token: Annotated[
            Optional[HTTPAuthorizationCredentials], Security(HTTPBearer(auto_error=False))
        ],
    ) -> None:
        if self._token is None:
            return
        if token is None:
            raise error_forbidden()
        if token.credentials != self._token:
            raise error_invalid_token()


async def get_project_member(
    session: AsyncSession, project_name: str, token: str
) -> Tuple[UserModel, ProjectModel]:
    user = await log_in_with_token(session=session, token=token)
    if user is None:
        raise error_invalid_token()
    project = await get_project_model_by_name(session=session, project_name=project_name)
    if project is None:
        raise error_not_found()
    if user.global_role == GlobalRole.ADMIN:
        return user, project
    project_role = get_user_project_role(user=user, project=project)
    if project_role is not None:
        return user, project
    raise error_forbidden()


async def is_project_member(session: AsyncSession, project_name: str, token: str) -> bool:
    try:
        await get_project_member(session, project_name, token)
        return True
    except HTTPException:
        return False
