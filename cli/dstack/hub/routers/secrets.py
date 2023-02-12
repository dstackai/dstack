from typing import List, Union

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer


from dstack.hub.security.scope import Scope
from dstack.core.repo import RepoAddress
from dstack.core.secret import Secret

router = APIRouter(prefix="/api/hub", tags=["secrets"])

security = HTTPBearer()


@router.get("/{hub_name}/secrets/get", dependencies=[Depends(Scope("secrets:get:write"))])
async def get_secrets(hub_name: str, repo_address: RepoAddress, secret_name: str):
    pass


@router.get("/{hub_name}/secrets/list", dependencies=[Depends(Scope("secrets:list:write"))], response_model=List[str])
async def list_secrets(hub_name: str, repo_address: RepoAddress):
    pass


@router.post("/{hub_name}/secrets/add", dependencies=[Depends(Scope("secrets:add:write"))])
async def add_secrets(hub_name: str, repo_address: RepoAddress, secret: Secret):
    pass


@router.post("/{hub_name}/secrets/update", dependencies=[Depends(Scope("secrets:update:write"))])
async def update_secrets(hub_name: str, repo_address: RepoAddress, secret: Secret):
    pass


@router.get("/{hub_name}/secrets/delete", dependencies=[Depends(Scope("secrets:delete:write"))])
async def delete_secrets(hub_name: str, repo_address: RepoAddress, secret_name: str):
    pass

