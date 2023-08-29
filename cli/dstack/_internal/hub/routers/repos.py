from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from dstack._internal.core.repo import RemoteRepoCredentials, RepoHead, RepoRef
from dstack._internal.hub.routers.util import call_backend, error_detail, get_project
from dstack._internal.hub.schemas import RepoHeadGet, ReposDelete, ReposUpdate, SaveRepoCredentials
from dstack._internal.hub.security.permissions import ProjectMember
from dstack._internal.hub.services.common import get_backends

router = APIRouter(prefix="/api/project", tags=["repos"], dependencies=[Depends(ProjectMember())])


@router.post("/{project_name}/repos/heads/list")
async def list_repo_heads(project_name: str) -> List[RepoHead]:
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)
    repo_id_to_repo_head_map = {}
    for _, backend in backends:
        repo_heads = await call_backend(backend.list_repo_heads)
        for repo_head in repo_heads:
            repo_id_to_repo_head_map[repo_head.repo_id] = repo_head
    return sorted(repo_id_to_repo_head_map.values(), key=lambda x: x.repo_id)


@router.post("/{project_name}/repos/heads/get")
async def get_repo_head(project_name: str, body: RepoHeadGet) -> RepoHead:
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)
    for _, backend in backends:
        repo_heads = await call_backend(backend.list_repo_heads)
        for repo_head in repo_heads:
            if repo_head.repo_id == body.repo_id:
                return repo_head
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=error_detail("Repo not found"),
    )


@router.post("/{project_name}/repos/credentials/save")
async def save_repo_credentials(project_name: str, body: SaveRepoCredentials):
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)
    for _, backend in backends:
        await call_backend(backend.save_repo_credentials, body.repo_id, body.repo_credentials)


@router.post(
    "/{project_name}/repos/credentials/get",
)
async def get_repo_credentials(project_name: str, repo_ref: RepoRef) -> RemoteRepoCredentials:
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)
    for _, backend in backends:
        repo_credentials = await call_backend(backend.get_repo_credentials, repo_ref.repo_id)
        if repo_credentials is not None:
            return repo_credentials
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=error_detail("Repo credentials not found"),
    )


@router.post("/{project_name}/repos/update")
async def update_repo(project_name: str, body: ReposUpdate):
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)
    for _, backend in backends:
        await call_backend(backend.update_repo_last_run_at, body.repo_spec, body.last_run_at)


@router.post("/{project_name}/repos/delete")
async def delete_repos(project_name: str, body: ReposDelete):
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)
    for _, backend in backends:
        for repo_id in body.repo_ids:
            await call_backend(backend.delete_repo, repo_id)
