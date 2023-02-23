from typing import List, Union

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

from dstack.core.repo import RepoAddress, RepoCredentials
from dstack.hub.models import ReposUpdate
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import get_hub
from dstack.hub.security.scope import Scope

router = APIRouter(prefix="/api/hub", tags=["repos"])

security = HTTPBearer()


@router.post("/{hub_name}/repos/update", dependencies=[Depends(Scope("repos:update:write"))])
async def update_repos(hub_name: str, body: ReposUpdate):
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    backend.update_repo_last_run_at(repo_address=body.repo_address, last_run_at=body.last_run_at)


@router.post(
    "/{hub_name}/repos/credentials", dependencies=[Depends(Scope("repos:credentials:write"))]
)
async def save_credentials_repos(
    hub_name: str, repo_address: RepoAddress, repo_credentials: RepoCredentials
):
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    backend.save_repo_credentials(repo_address=repo_address, repo_credentials=repo_credentials)


@router.get(
    "/{hub_name}/repos/credentials",
    dependencies=[Depends(Scope("repos:credentials:read"))],
    response_model=RepoCredentials,
)
async def get_credentials_repos(hub_name: str, repo_address: RepoAddress) -> RepoCredentials:
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    repo_credentials = backend.get_repo_credentials(repo_address=repo_address)
    return repo_credentials
