from typing import List, Union

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

from dstack.core.repo import RepoAddress, RepoCredentials, RepoProtocol
from dstack.hub.models import RepoAddress as RepoAddressHUB
from dstack.hub.models import RepoCredentials as RepoCredentialsHUB
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import get_hub
from dstack.hub.security.scope import Scope

router = APIRouter(prefix="/api/hub", tags=["repos"])

security = HTTPBearer()


@router.post("/{hub_name}/repos/poll", dependencies=[Depends(Scope("repos:update:write"))])
async def update_repos(hub_name: str, repo_address: RepoAddressHUB, last_run_at: int):
    pass


@router.post(
    "/{hub_name}/repos/credentials", dependencies=[Depends(Scope("repos:credentials:write"))]
)
async def save_credentials_repos(
    hub_name: str, repo_address: RepoAddressHUB, repo_credentials: RepoCredentialsHUB
):
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    backend.save_repo_credentials(
        repo_address=RepoAddress(
            repo_host_name=repo_address.repo_host_name,
            repo_port=repo_address.repo_port,
            repo_user_name=repo_address.repo_user_name,
            repo_name=repo_address.repo_name,
        ),
        repo_credentials=RepoCredentials(
            protocol=RepoProtocol(repo_credentials.protocol),
            private_key=repo_credentials.private_key,
            oauth_token=repo_credentials.oauth_token,
        ),
    )


@router.get(
    "/{hub_name}/repos/credentials",
    dependencies=[Depends(Scope("repos:credentials:read"))],
    response_model=RepoCredentialsHUB,
)
async def get_credentials_repos(hub_name: str, repo_address: RepoAddressHUB) -> RepoCredentialsHUB:
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    repo_credentials = backend.get_repo_credentials(
        repo_address=RepoAddress(
            repo_host_name=repo_address.repo_host_name,
            repo_port=repo_address.repo_port,
            repo_user_name=repo_address.repo_user_name,
            repo_name=repo_address.repo_name,
        )
    )
    return RepoCredentialsHUB(
        protocol=repo_credentials.protocol.value,
        private_key=repo_credentials.private_key,
        oauth_token=repo_credentials.oauth_token,
    )
