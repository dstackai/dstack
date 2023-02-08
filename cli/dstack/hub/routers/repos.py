from typing import List, Union

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

from dstack.hub.security.scope import Scope
from dstack.hub.models import RepoAddress, RepoCredentials

router = APIRouter(prefix="/api/hub", tags=["repos"])

security = HTTPBearer()


@router.post("/{hub_name}/repos/poll", dependencies=[Depends(Scope("repos:update:write"))])
async def update_repos(hub_name: str, repo_address: RepoAddress, last_run_at: int):
    pass


@router.post("/{hub_name}/repos/credentials", dependencies=[Depends(Scope("repos:credentials:write"))])
async def save_credentials_repos(hub_name: str, repo_address: RepoAddress, repo_credentials: RepoCredentials):
    pass


@router.get("/{hub_name}/repos/credentials", dependencies=[Depends(Scope("repos:credentials:write"))])
async def get_credentials_repos(hub_name: str, repo_address: RepoAddress, repo_credentials: RepoCredentials):
    pass
