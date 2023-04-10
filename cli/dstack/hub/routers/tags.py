from typing import List, Union

from fastapi import APIRouter, Depends, HTTPException, status

from dstack.core.repo import RepoAddress
from dstack.core.tag import TagHead
from dstack.hub.models import AddTagPath, AddTagRun
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import error_detail, get_project
from dstack.hub.security.permissions import ProjectMember

router = APIRouter(prefix="/api/project", tags=["tags"], dependencies=[Depends(ProjectMember())])


@router.post(
    "/{project_name}/tags/list/heads",
    response_model=List[TagHead],
)
async def list_heads_tags(project_name: str, repo_address: RepoAddress):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    list_tag = backend.list_tag_heads(repo_address=repo_address)
    return list_tag


@router.post(
    "/{project_name}/tags/{tag_name}",
    response_model=TagHead,
)
async def get_tag(project_name: str, tag_name: str, repo_address: RepoAddress) -> TagHead:
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    tag = backend.get_tag_head(repo_address=repo_address, tag_name=tag_name)
    if tag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=error_detail("Tag not found")
        )
    return tag


@router.post("/{project_name}/tags/{tag_name}/delete")
async def delete_tag(project_name: str, tag_name: str, repo_address: RepoAddress):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    tag = backend.get_tag_head(repo_address=repo_address, tag_name=tag_name)
    backend.delete_tag_head(repo_address=repo_address, tag_head=tag)


@router.post("/{project_name}/tags/add/run")
async def add_tag_from_run(project_name: str, body: AddTagRun):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    backend.add_tag_from_run(
        repo_address=body.repo_address,
        tag_name=body.tag_name,
        run_name=body.run_name,
        run_jobs=body.run_jobs,
    )


@router.post("/{project_name}/tags/add/path")
async def add_tag_from_path(project_name: str, body: AddTagPath):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    backend.add_tag_from_local_dirs(
        repo_data=body.repo_data, tag_name=body.tag_name, local_dirs=body.local_dirs
    )
