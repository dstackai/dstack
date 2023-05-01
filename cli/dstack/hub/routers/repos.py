from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from dstack.core.repo import RemoteRepoCredentials, RepoHead, RepoRef
from dstack.hub.models import RepoHeadGet, ReposUpdate, SaveRepoCredentials
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import error_detail, get_project
from dstack.hub.security.permissions import ProjectMember

router = APIRouter(prefix="/api/project", tags=["repos"], dependencies=[Depends(ProjectMember())])


@router.post("/{project_name}/repos/heads/list")
async def list_repo_heads(project_name: str) -> List[RepoHead]:
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    return backend.list_repo_heads()


@router.post("/{project_name}/repos/heads/get")
async def get_repo_head(project_name: str, body: RepoHeadGet) -> RepoHead:
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    repo_heads = backend.list_repo_heads()
    for repo_head in repo_heads:
        if repo_head.repo_id == body.repo_id:
            return repo_head
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=error_detail("Repo not found"),
    )


@router.post("/{project_name}/repos/credentials/save")
async def save_repo_credentials(
    project_name: str, save_repo_credentials_body: SaveRepoCredentials
):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    backend.save_repo_credentials(
        save_repo_credentials_body.repo_id,
        repo_credentials=save_repo_credentials_body.repo_credentials,
    )


@router.post(
    "/{project_name}/repos/credentials/get",
)
async def get_repo_credentials(project_name: str, repo_ref: RepoRef) -> RemoteRepoCredentials:
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    repo_credentials = backend.get_repo_credentials(repo_ref.repo_id)
    if repo_credentials is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("Repo credentials not found"),
        )
    return repo_credentials


@router.post("/{project_name}/repos/update")
async def update_repo(project_name: str, body: ReposUpdate):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    backend.update_repo_last_run_at(body.repo_spec, last_run_at=body.last_run_at)
