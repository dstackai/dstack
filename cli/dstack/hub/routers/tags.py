from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from dstack.core.repo import RepoRef
from dstack.core.tag import TagHead
from dstack.hub.models import AddTagPath, AddTagRun
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import error_detail, get_project
from dstack.hub.security.permissions import ProjectMember
from dstack.hub.utils.common import run_async

router = APIRouter(prefix="/api/project", tags=["tags"], dependencies=[Depends(ProjectMember())])


@router.post(
    "/{project_name}/tags/list/heads",
)
async def list_heads_tags(project_name: str, repo_ref: RepoRef) -> List[TagHead]:
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    tags = await run_async(backend.list_tag_heads, repo_ref.repo_id)
    return tags


@router.post(
    "/{project_name}/tags/{tag_name}",
    response_model=TagHead,
)
async def get_tag(project_name: str, tag_name: str, repo_ref: RepoRef) -> TagHead:
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    tag = await run_async(backend.get_tag_head, repo_ref.repo_id, tag_name)
    if tag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=error_detail("Tag not found")
        )
    return tag


@router.post("/{project_name}/tags/{tag_name}/delete")
async def delete_tag(project_name: str, tag_name: str, repo_ref: RepoRef):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    tag = await run_async(backend.get_tag_head, repo_ref.repo_id, tag_name)
    await run_async(backend.delete_tag_head, repo_ref.repo_id, tag)


@router.post("/{project_name}/tags/add/run")
async def add_tag_from_run(project_name: str, body: AddTagRun):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    # todo pass error to CLI if tag already exists
    await run_async(
        backend.add_tag_from_run, body.repo_id, body.tag_name, body.run_name, body.run_jobs
    )


@router.post("/{project_name}/tags/add/path")
async def add_tag_from_path(project_name: str, body: AddTagPath):
    # project = await get_project(project_name=project_name)
    # backend = get_backend(project)
    # backend.add_tag_from_local_dirs(tag_name=body.tag_name, local_dirs=body.local_dirs)
    raise NotImplementedError()
