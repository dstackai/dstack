from typing import Tuple

from fastapi import Depends, Security, status
from fastapi.security import HTTPBearer
from fastapi.security.http import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.services.projects import get_project_model_by_name
from dstack._internal.server.services.users import get_user_model_by_token
from dstack._internal.server.utils.routers import (
    raise_forbidden,
    raise_invalid_token,
    raise_not_found,
)


class Authenticated:
    async def __call__(
        self,
        session: AsyncSession = Depends(get_session),
        token: HTTPAuthorizationCredentials = Security(HTTPBearer()),
    ) -> UserModel:
        user = await get_user_model_by_token(session=session, token=token.credentials)
        if user is None:
            raise_invalid_token()
        return user


class GlobalAdmin:
    async def __call__(
        self,
        session: AsyncSession = Depends(get_session),
        token: HTTPAuthorizationCredentials = Security(HTTPBearer()),
    ) -> UserModel:
        user = await get_user_model_by_token(session=session, token=token.credentials)
        if user is None:
            raise_invalid_token()
        if user.global_role == GlobalRole.ADMIN:
            return user
        raise_forbidden()


class ProjectAdmin:
    async def __call__(
        self,
        project_name: str,
        session: AsyncSession = Depends(get_session),
        token: HTTPAuthorizationCredentials = Security(HTTPBearer()),
    ) -> Tuple[UserModel, ProjectModel]:
        user = await get_user_model_by_token(session=session, token=token.credentials)
        if user is None:
            raise_invalid_token()
        project = await get_project_model_by_name(session=session, project_name=project_name)
        for member in project.members:
            if member.user_id == user.id:
                if member.project_role == ProjectRole.ADMIN:
                    return user, project
                else:
                    raise_forbidden()
        raise_forbidden()


class ProjectMember:
    async def __call__(
        self,
        *,
        session: AsyncSession = Depends(get_session),
        project_name: str,
        token: HTTPAuthorizationCredentials = Security(HTTPBearer()),
    ) -> Tuple[UserModel, ProjectModel]:
        user = await get_user_model_by_token(session=session, token=token.credentials)
        if user is None:
            raise_invalid_token()
        project = await get_project_model_by_name(session=session, project_name=project_name)
        if project is None:
            raise_not_found()
        for member in project.members:
            if member.user_id == user.id:
                return user, project
        raise_forbidden()
