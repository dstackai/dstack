from typing import List, Union

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

from dstack.hub.models import RepoAddress, TagHead
from dstack.hub.security.scope import Scope

router = APIRouter(prefix="/api/hub", tags=["tags"])

security = HTTPBearer()


@router.get(
    "/{hub_name}/tags/list/heads",
    dependencies=[Depends(Scope("tags:list:read"))],
    response_model=List[TagHead],
)
async def list_heads_tags(hub_name: str, repo_address: RepoAddress):
    pass


@router.get(
    "/{hub_name}/tags/get", dependencies=[Depends(Scope("tags:get:read"))], response_model=TagHead
)
async def get_tags(hub_name: str, repo_address: RepoAddress, tag_name: str):
    pass


@router.get(
    "/{hub_name}/tags/delete",
    dependencies=[Depends(Scope("tags:delete:write"))],
    response_model=TagHead,
)
async def delete_tags(hub_name: str, repo_address: RepoAddress, tag_name: str):
    pass


@router.get("/{hub_name}/tags/add", dependencies=[Depends(Scope("tags:add:write"))])
async def add_tags(
    hub_name: str, repo_address: RepoAddress, tag_name: str, run_name: str, run_jobs: List[str]
):
    pass
