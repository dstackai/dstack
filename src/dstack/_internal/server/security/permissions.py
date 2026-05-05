from secrets import compare_digest
from typing import Annotated, Optional, Tuple
from uuid import UUID

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPBearer
from fastapi.security.http import HTTPAuthorizationCredentials
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.db import get_session
from dstack._internal.server.models import (
    ExportedFleetModel,
    ExportedGatewayModel,
    FleetModel,
    GatewayModel,
    ImportModel,
    InstanceModel,
    MemberModel,
    ProjectModel,
    UserModel,
)
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
from dstack._internal.utils.common import EntityName, EntityNameOrID


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


class ServiceAccount:
    def __init__(self, token: str) -> None:
        self._token = token.encode()

    async def __call__(
        self, token: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())]
    ) -> None:
        if not compare_digest(token.credentials.encode(), self._token):
            raise error_invalid_token()


class OptionalServiceAccount(ServiceAccount):
    _token: Optional[bytes] = None

    def __init__(self, token: Optional[str]) -> None:
        if token is not None:
            super().__init__(token)

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
        await super().__call__(token)


class AlwaysForbidden:
    async def __call__(self) -> None:
        raise error_forbidden()


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


async def check_can_access_fleet(
    session: AsyncSession,
    user: UserModel,
    fleet_project: ProjectModel,
    fleet_name_or_id: EntityNameOrID,
) -> None:
    if (
        user.global_role == GlobalRole.ADMIN
        or get_user_project_role(user=user, project=fleet_project) is not None
    ):
        return
    filters = [
        FleetModel.project_id == fleet_project.id,
        exists().where(
            MemberModel.user_id == user.id,
            MemberModel.project_id == ImportModel.project_id,
            ImportModel.export_id == ExportedFleetModel.export_id,
            ExportedFleetModel.fleet_id == FleetModel.id,
        ),
    ]
    if isinstance(fleet_name_or_id, EntityName):
        filters.extend([FleetModel.name == fleet_name_or_id.name, FleetModel.deleted == False])
    else:
        filters.append(FleetModel.id == fleet_name_or_id.id)
    res = await session.execute(select(func.count()).select_from(FleetModel).where(*filters))
    if res.scalar_one() == 0:
        raise error_forbidden()


async def check_can_access_gateway(
    session: AsyncSession,
    user: UserModel,
    gateway_project: ProjectModel,
    gateway_name: str,
) -> None:
    if (
        user.global_role == GlobalRole.ADMIN
        or get_user_project_role(user=user, project=gateway_project) is not None
    ):
        return
    filters = [
        GatewayModel.project_id == gateway_project.id,
        GatewayModel.name == gateway_name,
        exists().where(
            MemberModel.user_id == user.id,
            MemberModel.project_id == ImportModel.project_id,
            ImportModel.export_id == ExportedGatewayModel.export_id,
            ExportedGatewayModel.gateway_id == GatewayModel.id,
        ),
    ]
    res = await session.execute(select(func.count()).select_from(GatewayModel).where(*filters))
    if res.scalar_one() == 0:
        raise error_forbidden()


async def check_can_access_instance(
    session: AsyncSession,
    user: UserModel,
    instance_project: ProjectModel,
    instance_id: UUID,
) -> None:
    if (
        user.global_role == GlobalRole.ADMIN
        or get_user_project_role(user=user, project=instance_project) is not None
    ):
        return
    filters = [
        InstanceModel.project_id == instance_project.id,
        InstanceModel.id == instance_id,
        exists().where(
            MemberModel.user_id == user.id,
            MemberModel.project_id == ImportModel.project_id,
            ImportModel.export_id == ExportedFleetModel.export_id,
            ExportedFleetModel.fleet_id == InstanceModel.fleet_id,
        ),
    ]
    res = await session.execute(select(func.count()).select_from(InstanceModel).where(*filters))
    if res.scalar_one() == 0:
        raise error_forbidden()
