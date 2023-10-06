from typing import List, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import BackendInvalidCredentialsError, BackendNotAvailable
from dstack._internal.core.models.backends import (
    AnyConfigInfoWithCreds,
    AnyConfigInfoWithCredsPartial,
    AnyConfigValues,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.backends import DeleteBackendsRequest
from dstack._internal.server.security.permissions import Authenticated, ProjectAdmin, ProjectMember
from dstack._internal.server.services import backends
from dstack._internal.server.utils.routers import raise_not_found, raise_server_client_error

root_router = APIRouter(prefix="/api/backends", tags=["backends"])
project_router = APIRouter(prefix="/api/project/{project_name}/backends", tags=["backends"])


@root_router.post("/list_types")
async def list_backend_types() -> List[BackendType]:
    return backends.list_available_backend_types()


@root_router.post("/config_values")
async def get_backend_config_values(
    body: AnyConfigInfoWithCredsPartial,
    user: UserModel = Depends(Authenticated()),
) -> AnyConfigValues:
    return await backends.get_backend_config_values(config=body)


@project_router.post("/create")
async def create_backend(
    body: AnyConfigInfoWithCreds,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
) -> AnyConfigInfoWithCreds:
    _, project = user_project
    return await backends.create_backend(session=session, project=project, config=body)


@project_router.post("/update")
async def update_backend(
    body: AnyConfigInfoWithCreds,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
) -> AnyConfigInfoWithCreds:
    _, project = user_project
    return await backends.update_backend(session=session, project=project, config=body)


@project_router.post("/delete")
async def delete_backends(
    body: DeleteBackendsRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
):
    _, project = user_project
    await backends.delete_backends(
        session=session, project=project, backends_types=body.backends_names
    )


@project_router.post("/{backend_name}/config_info")
async def get_backend_config_info(
    backend_name: BackendType,
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
) -> AnyConfigInfoWithCreds:
    _, project = user_project
    config_info = await backends.get_config_info(project=project, backend_type=backend_name)
    if config_info is None:
        raise_not_found()
    return config_info
