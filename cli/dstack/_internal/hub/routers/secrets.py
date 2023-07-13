from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from dstack._internal.core.repo import RepoRef
from dstack._internal.core.secret import Secret
from dstack._internal.hub.models import SecretAddUpdate
from dstack._internal.hub.routers.util import error_detail, get_backend, get_project
from dstack._internal.hub.security.permissions import ProjectMember
from dstack._internal.hub.utils.common import run_async

router = APIRouter(
    prefix="/api/project", tags=["secrets"], dependencies=[Depends(ProjectMember())]
)


@router.post("/{project_name}/secrets/list")
async def list_secrets(project_name: str, repo_ref: RepoRef) -> List[str]:
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    secrets_names = await run_async(backend.list_secret_names, repo_ref.repo_id)
    return secrets_names


@router.post("/{project_name}/secrets/add")
async def add_secret(project_name: str, body: SecretAddUpdate):
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    await run_async(backend.add_secret, body.repo_id, body.secret)


@router.post("/{project_name}/secrets/update")
async def update_secret(project_name: str, body: SecretAddUpdate):
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    await run_async(backend.update_secret, body.repo_id, body.secret)


@router.post("/{project_name}/secrets/{secret_name}/get")
async def get_secret(project_name: str, secret_name: str, repo_ref: RepoRef) -> Secret:
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    secret = await run_async(backend.get_secret, repo_ref.repo_id, secret_name)
    if secret is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=error_detail("Secret not found")
        )
    return secret


@router.post("/{project_name}/secrets/{secret_name}/delete")
async def delete_secret(project_name: str, secret_name: str, repo_ref: RepoRef):
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    await run_async(backend.delete_secret, repo_ref.repo_id, secret_name)
