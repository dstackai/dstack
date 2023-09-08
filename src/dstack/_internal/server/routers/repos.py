from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from dstack._internal.core.models.repos import RemoteRepoCredentials, Repo, RepoRef
from dstack._internal.server.schemas.repos import (
    DeleteReposRequest,
    GetRepoCredentialsRequest,
    GetRepoRequest,
    SaveRepoCredentialsRequest,
)

router = APIRouter(prefix="/api/project/{project_name}/repos", tags=["repos"])


@router.post("/list")
async def list_repos(project_name: str) -> List[Repo]:
    pass


@router.post("/get")
async def get_repo(project_name: str, body: GetRepoRequest) -> Repo:
    pass


@router.post("/save_credentials")
async def save_repo_credentials(project_name: str, body: SaveRepoCredentialsRequest):
    pass


@router.post("/get_credentials")
async def get_repo_credentials(
    project_name: str, body: GetRepoCredentialsRequest
) -> RemoteRepoCredentials:
    pass


@router.post("/delete")
async def delete_repos(project_name: str, body: DeleteReposRequest):
    pass
