from typing import List, Optional

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

from dstack.core.repo import RepoAddress
from dstack.core.secret import Secret
from dstack.hub.models import SecretAddUpdate
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import get_hub
from dstack.hub.security.scope import Scope

router = APIRouter(prefix="/api/hub", tags=["secrets"])

security = HTTPBearer()


@router.get(
    "/{hub_name}/secrets/get/{secret_name}",
    dependencies=[Depends(Scope("secrets:get:write"))],
    response_model=Secret,
)
async def get_secrets(hub_name: str, secret_name: str, repo_address: RepoAddress) -> Secret:
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    return backend.get_secret(repo_address=repo_address, secret_name=secret_name)


@router.get(
    "/{hub_name}/secrets/list",
    dependencies=[Depends(Scope("secrets:list:write"))],
    response_model=Optional[List[str]],
)
async def list_secrets(hub_name: str, repo_address: RepoAddress) -> List[str]:
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    return backend.list_secret_names(repo_address=repo_address)


@router.post("/{hub_name}/secrets/add", dependencies=[Depends(Scope("secrets:add:write"))])
async def add_secrets(hub_name: str, body: SecretAddUpdate):
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    backend.add_secret(repo_address=body.repo_address, secret=body.secret)


@router.post("/{hub_name}/secrets/update", dependencies=[Depends(Scope("secrets:update:write"))])
async def update_secrets(hub_name: str, body: SecretAddUpdate):
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    backend.update_secret(repo_address=body.repo_address, secret=body.secret)


@router.post(
    "/{hub_name}/secrets/delete/{secret_name}",
    dependencies=[Depends(Scope("secrets:delete:write"))],
)
async def delete_secrets(hub_name: str, secret_name: str, repo_address: RepoAddress):
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    backend.delete_secret(repo_address=repo_address, secret_name=secret_name)
