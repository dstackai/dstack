from typing import List, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.repos import (
    AnyRepoHead,
    RemoteRepoCreds,
    RepoHead,
    RepoHeadWithCreds,
)
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.repos import (
    DeleteReposRequest,
    GetRepoCredsRequest,
    GetRepoRequest,
    SaveRepoCredsRequest,
)
from dstack._internal.server.security.permissions import ProjectMember
from dstack._internal.server.services import repos

router = APIRouter(prefix="/api/project/{project_name}/repos", tags=["repos"])


@router.post("/list")
async def list_repos(
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> List[RepoHead]:
    _, project = user_project
    return await repos.list_repos(session=session, project=project)


@router.post("/get")
async def get_repo(
    body: GetRepoRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> RepoHeadWithCreds:
    _, project = user_project
    repo = await repos.get_repo(
        session=session,
        project=project,
        repo_id=body.repo_id,
        include_creds=body.include_creds,
    )
    return repo


@router.post("/init")
async def init_repo(
    project_name: str,
    body: SaveRepoCredsRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    _, project = user_project
    await repos.init_repo(
        session=session,
        project=project,
        repo_id=body.repo_id,
        repo_info=body.repo_info,
        repo_creds=body.repo_creds,
    )


@router.post("/delete")
async def delete_repos(project_name: str, body: DeleteReposRequest):
    pass
