from typing import List, Optional

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

from dstack.core.repo import RepoAddress
from dstack.core.secret import Secret
from dstack.hub.models import SecretAddUpdate
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import get_project
from dstack.hub.security.scope import Scope

router = APIRouter(prefix="/api/project", tags=["secrets"])

security = HTTPBearer()


@router.get(
    "/{project_name}/secrets/get/{secret_name}",
    dependencies=[Depends(Scope("secrets:get:write"))],
    response_model=Secret,
)
async def get_secrets(project_name: str, secret_name: str, repo_address: RepoAddress) -> Secret:
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    return backend.get_secret(repo_address=repo_address, secret_name=secret_name)


@router.get(
    "/{project_name}/secrets/list",
    dependencies=[Depends(Scope("secrets:list:write"))],
    response_model=Optional[List[str]],
)
async def list_secrets(project_name: str, repo_address: RepoAddress) -> List[str]:
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    return backend.list_secret_names(repo_address=repo_address)


@router.post("/{project_name}/secrets/add", dependencies=[Depends(Scope("secrets:add:write"))])
async def add_secrets(project_name: str, body: SecretAddUpdate):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    backend.add_secret(repo_address=body.repo_address, secret=body.secret)


@router.post(
    "/{project_name}/secrets/update", dependencies=[Depends(Scope("secrets:update:write"))]
)
async def update_secrets(project_name: str, body: SecretAddUpdate):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    backend.update_secret(repo_address=body.repo_address, secret=body.secret)


@router.post(
    "/{project_name}/secrets/delete/{secret_name}",
    dependencies=[Depends(Scope("secrets:delete:write"))],
)
async def delete_secrets(project_name: str, secret_name: str, repo_address: RepoAddress):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    backend.delete_secret(repo_address=repo_address, secret_name=secret_name)
