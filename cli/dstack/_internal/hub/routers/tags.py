from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from dstack._internal.core.repo import RepoRef
from dstack._internal.core.tag import TagHead
from dstack._internal.hub.routers.util import (
    call_backend,
    error_detail,
    get_project,
    get_run_backend,
)
from dstack._internal.hub.schemas import AddTagPath, AddTagRun
from dstack._internal.hub.security.permissions import ProjectMember
from dstack._internal.hub.services.common import get_backends

router = APIRouter(prefix="/api/project", tags=["tags"], dependencies=[Depends(ProjectMember())])


@router.post(
    "/{project_name}/tags/list/heads",
)
async def list_heads_tags(project_name: str, repo_ref: RepoRef) -> List[TagHead]:
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)
    tags = []
    for _, backend in backends:
        tags += await call_backend(backend.list_tag_heads, repo_ref.repo_id)
    return tags


@router.post(
    "/{project_name}/tags/{tag_name}",
    response_model=TagHead,
)
async def get_tag(project_name: str, tag_name: str, repo_ref: RepoRef) -> TagHead:
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)
    for _, backend in backends:
        tag = await call_backend(backend.get_tag_head, repo_ref.repo_id, tag_name)
        if tag is not None:
            return tag
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=error_detail("Tag not found")
    )


@router.post("/{project_name}/tags/{tag_name}/delete")
async def delete_tag(project_name: str, tag_name: str, repo_ref: RepoRef):
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)
    for _, backend in backends:
        tag = await call_backend(backend.get_tag_head, repo_ref.repo_id, tag_name)
        await call_backend(backend.delete_tag_head, repo_ref.repo_id, tag)


@router.post("/{project_name}/tags/add/run")
async def add_tag_from_run(project_name: str, body: AddTagRun):
    project = await get_project(project_name=project_name)
    backend = await get_run_backend(project, body.repo_id, body.run_name)
    # todo pass error to CLI if tag already exists
    await call_backend(
        backend.add_tag_from_run, body.repo_id, body.tag_name, body.run_name, body.run_jobs
    )


@router.post("/{project_name}/tags/add/path")
async def add_tag_from_path(project_name: str, body: AddTagPath):
    # project = await get_project(project_name=project_name)
    # backend = await get_backend(project)
    # backend.add_tag_from_local_dirs(tag_name=body.tag_name, local_dirs=body.local_dirs)
    raise NotImplementedError()
