from typing import List, Union

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

from dstack.core.repo import RepoAddress, RepoCredentials
from dstack.hub.models import ReposUpdate
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import get_project
from dstack.hub.security.scope import Scope

router = APIRouter(prefix="/api/project", tags=["repos"])

security = HTTPBearer()


@router.post("/{project_name}/repos/update", dependencies=[Depends(Scope("repos:update:write"))])
async def update_repos(project_name: str, body: ReposUpdate):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    backend.update_repo_last_run_at(repo_address=body.repo_address, last_run_at=body.last_run_at)


@router.post(
    "/{project_name}/repos/credentials", dependencies=[Depends(Scope("repos:credentials:write"))]
)
async def save_credentials_repos(
    project_name: str, repo_address: RepoAddress, repo_credentials: RepoCredentials
):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    backend.save_repo_credentials(repo_address=repo_address, repo_credentials=repo_credentials)


@router.get(
    "/{project_name}/repos/credentials",
    dependencies=[Depends(Scope("repos:credentials:read"))],
    response_model=RepoCredentials,
)
async def get_credentials_repos(project_name: str, repo_address: RepoAddress) -> RepoCredentials:
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    repo_credentials = backend.get_repo_credentials(repo_address=repo_address)
    return repo_credentials
