from typing import Dict, Optional, Tuple

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


async def get_backend_by_type(project: Project, backend_type: str) -> Tuple[DBBackend, Backend]:
    backends = await backends_cache.get_project_backends(project)
    for db_backend, backend in backends:
        if db_backend.type == backend_type:
            return db_backend, backend
    _raise_backend_not_available_error(backend_type)


async def get_run_backend(
    project: Project, repo_id: str, run_name: str
) -> Tuple[Optional[DBBackend], Optional[Backend]]:
    backends = await backends_cache.get_project_backends(project)
    for db_backend, backend in backends:
        run_head = await call_backend(backend.get_run_head, repo_id, run_name)
        if run_head is not None:
            return db_backend, backend
    return None, None


async def get_job_backend(
    project: Project, repo_id: str, job_id: str
) -> Tuple[Optional[DBBackend], Optional[Backend]]:
    backends = await backends_cache.get_project_backends(project)
    for db_backend, backend in backends:
        job_heads = await call_backend(backend.list_job_heads, repo_id)
        job_ids = [job_head.job_id for job_head in job_heads]
        if job_id in job_ids:
            return db_backend, backend
    return None, None


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


def _raise_backend_not_available_error(backend_type: str):
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=error_detail(
            f"Backend {backend_type} not available. Ensure the dependencies for {backend_type} are installed.",
            code=BackendNotAvailableError.code,
        ),
    )
