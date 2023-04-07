from typing import List, Union

from fastapi import APIRouter, Depends

from dstack.core.repo import RepoAddress
from dstack.core.tag import TagHead
from dstack.hub.models import AddTagPath, AddTagRun
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import get_project
from dstack.hub.security.permissions import ProjectMember

router = APIRouter(prefix="/api/project", tags=["tags"], dependencies=[Depends(ProjectMember())])


@router.get(
    "/{project_name}/tags/list/heads",
    response_model=List[TagHead],
)
async def list_heads_tags(project_name: str, repo_address: RepoAddress):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    list_tag = backend.list_tag_heads(repo_address=repo_address)
    return list_tag


@router.get(
    "/{project_name}/tags/{tag_name}",
    response_model=TagHead,
)
async def get_tags(project_name: str, tag_name: str, repo_address: RepoAddress):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    tag = backend.get_tag_head(repo_address=repo_address, tag_name=tag_name)
    return tag


@router.post("/{project_name}/tags/{tag_name}/delete")
async def delete_tags(project_name: str, tag_name: str, repo_address: RepoAddress):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    tag = backend.get_tag_head(repo_address=repo_address, tag_name=tag_name)
    backend.delete_tag_head(repo_address=repo_address, tag_head=tag)


@router.post("/{project_name}/tags/add/run")
async def add_tags(project_name: str, body: AddTagRun):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    backend.add_tag_from_run(
        repo_address=body.repo_address,
        tag_name=body.tag_name,
        run_name=body.run_name,
        run_jobs=body.run_jobs,
    )


@router.post("/{project_name}/tags/add/path")
async def add_tags(project_name: str, body: AddTagPath):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    backend.add_tag_from_local_dirs(
        repo_data=body.repo_data, tag_name=body.tag_name, local_dirs=body.local_dirs
    )
