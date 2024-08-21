from typing import Tuple

from fastapi import Depends, Security
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
            raise error_forbidden()
        if user.global_role == GlobalRole.ADMIN:
            return user, project
        project_role = get_user_project_role(user=user, project=project)
        if project_role == ProjectRole.ADMIN:
            return user, project
        raise error_forbidden()


class ProjectManager:
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
            raise error_forbidden()
        if user.global_role in GlobalRole.ADMIN:
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
