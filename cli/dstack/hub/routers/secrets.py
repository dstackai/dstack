from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from dstack.core.repo import RepoAddress
from dstack.core.secret import Secret
from dstack.hub.models import SecretAddUpdate
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import error_detail, get_project
from dstack.hub.security.permissions import ProjectMember

router = APIRouter(
    prefix="/api/project", tags=["secrets"], dependencies=[Depends(ProjectMember())]
)


@router.post("/{project_name}/secrets/list")
async def list_secrets(project_name: str, repo_address: RepoAddress) -> List[str]:
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    return backend.list_secret_names(repo_address=repo_address)


@router.post("/{project_name}/secrets/add")
async def add_secret(project_name: str, body: SecretAddUpdate):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    backend.add_secret(repo_address=body.repo_address, secret=body.secret)


@router.post("/{project_name}/secrets/update")
async def update_secret(project_name: str, body: SecretAddUpdate):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    backend.update_secret(repo_address=body.repo_address, secret=body.secret)


@router.post("/{project_name}/secrets/{secret_name}/get")
async def get_secret(project_name: str, secret_name: str, repo_address: RepoAddress) -> Secret:
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    secret = backend.get_secret(repo_address=repo_address, secret_name=secret_name)
    if secret is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=error_detail("Secret not found")
        )
    return secret


@router.post("/{project_name}/secrets/{secret_name}/delete")
async def delete_secret(project_name: str, secret_name: str, repo_address: RepoAddress):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    backend.delete_secret(repo_address=repo_address, secret_name=secret_name)
