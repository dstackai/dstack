from typing import List, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.core.backends.configurators
from dstack._internal.core.backends.models import (
    AnyBackendConfigWithCreds,
    BackendInfoYAML,
)
from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.server import settings
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.backends import (
    CreateBackendYAMLRequest,
    DeleteBackendsRequest,
    UpdateBackendYAMLRequest,
)
from dstack._internal.server.security.permissions import ProjectAdmin
from dstack._internal.server.services import backends
from dstack._internal.server.services.backends import handlers as backends_handlers
from dstack._internal.server.services.config import (
    ServerConfigManager,
    create_backend_config_yaml,
    get_backend_config_yaml,
    update_backend_config_yaml,
)
from dstack._internal.server.utils.routers import get_base_api_additional_responses

root_router = APIRouter(
    prefix="/api/backends",
    tags=["backends"],
    responses=get_base_api_additional_responses(),
)
project_router = APIRouter(
    prefix="/api/project/{project_name}/backends",
    tags=["backends"],
    responses=get_base_api_additional_responses(),
)


@root_router.post("/list_types")
async def list_backend_types() -> List[BackendType]:
    return dstack._internal.core.backends.configurators.list_available_backend_types()


@project_router.post("/create")
async def create_backend(
    body: AnyBackendConfigWithCreds,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
) -> AnyBackendConfigWithCreds:
    _, project = user_project
    config = await backends.create_backend(session=session, project=project, config=body)
    if settings.SERVER_CONFIG_ENABLED:
        await ServerConfigManager().sync_config(session=session)
    return config


@project_router.post("/update")
async def update_backend(
    body: AnyBackendConfigWithCreds,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
) -> AnyBackendConfigWithCreds:
    _, project = user_project
    config = await backends.update_backend(session=session, project=project, config=body)
    if settings.SERVER_CONFIG_ENABLED:
        await ServerConfigManager().sync_config(session=session)
    return config


@project_router.post("/delete")
async def delete_backends(
    body: DeleteBackendsRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
):
    _, project = user_project
    await backends_handlers.delete_backends_safe(
        session=session, project=project, backends_types=body.backends_names, error=True
    )
    if settings.SERVER_CONFIG_ENABLED:
        await ServerConfigManager().sync_config(session=session)


@project_router.post("/{backend_name}/config_info")
async def get_backend_config_info(
    backend_name: BackendType,
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
) -> AnyBackendConfigWithCreds:
    _, project = user_project
    config = await backends.get_backend_config(project=project, backend_type=backend_name)
    if config is None:
        raise ResourceNotExistsError()
    return config


@project_router.post("/create_yaml")
async def create_backend_yaml(
    body: CreateBackendYAMLRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
):
    _, project = user_project
    await create_backend_config_yaml(
        session=session,
        project=project,
        config_yaml=body.config_yaml,
    )


@project_router.post("/update_yaml")
async def update_backend_yaml(
    body: UpdateBackendYAMLRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
):
    _, project = user_project
    await update_backend_config_yaml(
        session=session,
        project=project,
        config_yaml=body.config_yaml,
    )


@project_router.post("/{backend_name}/get_yaml")
async def get_backend_yaml(
    backend_name: BackendType,
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
) -> BackendInfoYAML:
    _, project = user_project
    return await get_backend_config_yaml(project=project, backend_type=backend_name)
