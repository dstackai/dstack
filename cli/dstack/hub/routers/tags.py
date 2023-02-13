from typing import List, Union

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

from dstack.core.repo import RepoAddress
from dstack.core.tag import TagHead
from dstack.hub.models import AddTagPath, AddTagRun
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import get_hub
from dstack.hub.security.scope import Scope

router = APIRouter(prefix="/api/hub", tags=["tags"])

security = HTTPBearer()


@router.get(
    "/{hub_name}/tags/list/heads",
    dependencies=[Depends(Scope("tags:list:read"))],
    response_model=List[TagHead],
)
async def list_heads_tags(hub_name: str, repo_address: RepoAddress):
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    list_tag = backend.list_tag_heads(repo_address=repo_address)
    return list_tag


@router.get(
    "/{hub_name}/tags/{tag_name}",
    dependencies=[Depends(Scope("tags:get:read"))],
    response_model=TagHead,
)
async def get_tags(hub_name: str, tag_name: str, repo_address: RepoAddress):
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    tag = backend.get_tag_head(repo_address=repo_address, tag_name=tag_name)
    return tag


@router.post(
    "/{hub_name}/tags/{tag_name}/delete", dependencies=[Depends(Scope("tags:delete:write"))]
)
async def delete_tags(hub_name: str, tag_name: str, repo_address: RepoAddress):
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    tag = backend.get_tag_head(repo_address=repo_address, tag_name=tag_name)
    backend.delete_tag_head(repo_address=repo_address, tag_head=tag)


@router.post("/{hub_name}/tags/add/run", dependencies=[Depends(Scope("tags:add:write"))])
async def add_tags(hub_name: str, body: AddTagRun):
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    backend.add_tag_from_run(
        repo_address=body.repo_address,
        tag_name=body.tag_name,
        run_name=body.run_name,
        run_jobs=body.run_jobs,
    )


@router.post("/{hub_name}/tags/add/path", dependencies=[Depends(Scope("tags:add:write"))])
async def add_tags(hub_name: str, body: AddTagPath):
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    backend.add_tag_from_local_dirs(
        repo_data=body.repo_data, tag_name=body.tag_name, local_dirs=body.local_dirs
    )
