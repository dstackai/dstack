from typing import Dict, Optional

from fastapi import HTTPException, status

from dstack._internal.backend.base import Backend
from dstack._internal.core.error import BackendAuthError
from dstack._internal.hub.models import Project
from dstack._internal.hub.repository.projects import ProjectManager
from dstack._internal.hub.services.backends import cache as backends_cache
from dstack._internal.hub.services.backends import get_configurator
from dstack._internal.hub.services.backends.base import Configurator


async def get_project(project_name: str) -> Project:
    project = await ProjectManager.get(name=project_name)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("Project not found"),
        )
    _check_backend_avaialble(project)
    return project


async def get_backend(project: Project) -> Optional[Backend]:
    try:
        return await backends_cache.get_backend(project)
    except BackendAuthError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(BackendAuthError.message, code=BackendAuthError.code),
        )


def get_backend_configurator(backend_type: str) -> Configurator:
    configurator = get_configurator(backend_type)
    if configurator is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(f"Backend {backend_type} not available"),
        )
    return configurator


def _check_backend_avaialble(project: Project):
    get_backend_configurator(project.backend)


def error_detail(msg: str, code: Optional[str] = None, **kwargs) -> Dict:
    return {
        "msg": msg,
        "code": code,
        **kwargs,
    }
