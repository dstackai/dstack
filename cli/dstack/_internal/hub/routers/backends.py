from typing import List, Tuple

from fastapi import APIRouter, Depends, HTTPException, status

from dstack._internal.backend.base import Backend
from dstack._internal.hub.db.models import Project, User
from dstack._internal.hub.repository.projects import ProjectManager
from dstack._internal.hub.routers.util import (
    call_backend,
    error_detail,
    get_backend_by_type,
    get_backend_configurator,
)
from dstack._internal.hub.schemas import (
    BackendConfigWithCreds,
    BackendConfigWithCredsPartial,
    BackendInfo,
    BackendInfoWithCreds,
    BackendsDelete,
    BackendType,
    BackendValues,
)
from dstack._internal.hub.security.permissions import Authenticated, ProjectAdmin, ProjectMember
from dstack._internal.hub.services.backends import list_avaialble_backend_types
from dstack._internal.hub.services.backends.base import BackendConfigError
from dstack._internal.hub.services.backends.cache import clear_backend_cache
from dstack._internal.hub.services.common import get_backends
from dstack._internal.hub.utils.common import run_async

root_router = APIRouter(
    prefix="/api/backends", tags=["backends"], dependencies=[Depends(Authenticated())]
)
project_router = APIRouter(
    prefix="/api/project", tags=["backends"], dependencies=[Depends(ProjectMember())]
)


@root_router.post("/list_types")
async def list_backend_types() -> List[BackendType]:
    return list_avaialble_backend_types()


@root_router.post("/config_values")
async def get_backend_config_values(
    config: BackendConfigWithCredsPartial,
    user: User = Depends(Authenticated()),
) -> BackendValues:
    configurator = get_backend_configurator(config.__root__.type)
    try:
        result = await run_async(configurator.configure_backend, config.__root__)
    except BackendConfigError as e:
        _error_response_on_config_error(e, path_to_config=[])
    return result


@project_router.post("/{project_name}/backends/list")
async def list_backends(user_project: User = Depends(ProjectMember())) -> List[BackendInfo]:
    _, project = user_project
    return await ProjectManager.list_backend_infos(project=project)


@project_router.post("/{project_name}/backends/create")
async def create_backend(
    backend_config: BackendConfigWithCreds, user_project: User = Depends(ProjectMember())
) -> BackendConfigWithCreds:
    _, project = user_project
    backend = await ProjectManager.get_backend(
        project=project, backend_name=backend_config.__root__.type
    )
    if backend is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=[
                error_detail(
                    f"{backend.type} backend exists", code="backend_not_unique", loc=["type"]
                )
            ],
        )
    configurator = get_backend_configurator(backend_config.__root__.type)
    try:
        await run_async(configurator.configure_backend, backend_config.__root__)
        await ProjectManager.create_backend(
            project=project, backend_config=backend_config.__root__
        )
    except BackendConfigError as e:
        _error_response_on_config_error(e, path_to_config=[])
    # refetch project to include new backend
    project = await ProjectManager.get(project.name)
    clear_backend_cache(project.name)
    await _sync_backend(project, backend_config.__root__.type)
    return backend_config


@project_router.post("/{project_name}/backends/update")
async def update_backend(
    backend_config: BackendConfigWithCreds,
    user_project: Tuple[User, Project] = Depends(ProjectAdmin()),
) -> BackendConfigWithCreds:
    _, project = user_project
    configurator = get_backend_configurator(backend_config.__root__.type)
    try:
        await run_async(configurator.configure_backend, backend_config.__root__)
        await ProjectManager.update_backend(
            project=project, backend_config=backend_config.__root__
        )
    except BackendConfigError as e:
        _error_response_on_config_error(e, path_to_config=["backend"])
    # refetch project to include new backend
    project = await ProjectManager.get(project.name)
    clear_backend_cache(project.name)
    await _sync_backend(project, backend_config.__root__.type)
    return backend_config


@project_router.post("/{project_name}/backends/delete")
async def delete_backends(
    body: BackendsDelete,
    user_project: Tuple[User, Project] = Depends(ProjectAdmin()),
):
    _, project = user_project
    for backend_name in body.backends:
        await ProjectManager.delete_backend(project=project, backend_name=backend_name)
    clear_backend_cache(project.name)


@project_router.post("/{project_name}/backends/{backend_name}/config_info")
async def get_backend_config_info(
    backend_name: str, user_project: Tuple[User, Project] = Depends(ProjectAdmin())
) -> BackendInfoWithCreds:
    _, project = user_project
    project_info = await ProjectManager.get_backend_info(
        project=project, backend_name=backend_name
    )
    return project_info


async def _sync_backend(project: Project, backend_type: str):
    _, target_backend = await get_backend_by_type(project, backend_type)
    backends = await get_backends(project)
    if len(backends) == 1:
        return
    for db_backend, backend in backends:
        if db_backend.type != backend_type:
            await _sync_credentials(backend, target_backend)
            await _sync_secrets(backend, target_backend)
            return


async def _sync_credentials(source_backend: Backend, target_backend: Backend):
    repo_heads = await call_backend(source_backend.list_repo_heads)
    for repo_head in repo_heads:
        repo_creds = await call_backend(source_backend.get_repo_credentials, repo_head.repo_id)
        if repo_creds is not None:
            await call_backend(target_backend.save_repo_credentials, repo_head.repo_id, repo_creds)


async def _sync_secrets(source_backend: Backend, target_backend: Backend):
    repo_heads = await call_backend(source_backend.list_repo_heads)
    for repo_head in repo_heads:
        secret_names = await call_backend(source_backend.list_secret_names, repo_head.repo_id)
        for secret_name in secret_names:
            secret = await call_backend(target_backend.get_secret, repo_head.repo_id, secret_name)
            if secret is not None:
                continue
            secret = await call_backend(source_backend.get_secret, repo_head.repo_id, secret_name)
            if secret is not None:
                await call_backend(target_backend.add_secret, repo_head.repo_id, secret)


def _error_response_on_config_error(e: BackendConfigError, path_to_config: List[str]):
    if len(e.fields) > 0:
        error_details = [
            error_detail(e.message, code=e.code, loc=path_to_config + f) for f in e.fields
        ]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_details,
        )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=[error_detail(e.message, code=e.code)],
    )
