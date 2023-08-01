from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException, status

from dstack._internal.backend.base import Backend
from dstack._internal.core.error import BackendNotAvailableError, BackendValueError
from dstack._internal.hub.db.models import Backend as DBBackend
from dstack._internal.hub.db.models import Project
from dstack._internal.hub.repository.projects import ProjectManager
from dstack._internal.hub.services.backends import cache as backends_cache
from dstack._internal.hub.services.backends import get_configurator
from dstack._internal.hub.services.backends.base import Configurator
from dstack._internal.hub.utils.common import run_async


async def get_project(project_name: str) -> Project:
    project = await ProjectManager.get(name=project_name)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("Project not found"),
        )
    return project


async def get_backends(project: Project) -> List[Tuple[DBBackend, Backend]]:
    return await backends_cache.get_backends(project)


def get_backend_configurator(backend_type: str) -> Configurator:
    configurator = get_configurator(backend_type)
    if configurator is None:
        _raise_backend_not_available_error(backend_type)
    return configurator


def error_detail(msg: str, code: Optional[str] = None, **kwargs) -> Dict:
    return {
        "msg": msg,
        "code": code,
        **kwargs,
    }


async def call_backend(func, *args):
    try:
        return await run_async(func, *args)
    except BackendValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(e.message, code=e.code),
        )


def _check_backend_avaialble(project: Project):
    get_backend_configurator(project.backend)


def _raise_backend_not_available_error(backend_type: str):
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=error_detail(
            f"Backend {backend_type} not available. Ensure the dependencies for {backend_type} are installed.",
            code=BackendNotAvailableError.code,
        ),
    )
