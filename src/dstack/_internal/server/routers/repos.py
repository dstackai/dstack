from typing import List, Tuple

from fastapi import APIRouter, Depends, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ResourceNotExistsError, ServerClientError
from dstack._internal.core.models.repos import RepoHead, RepoHeadWithCreds
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.repos import (
    DeleteReposRequest,
    GetRepoRequest,
    SaveRepoCredsRequest,
)
from dstack._internal.server.security.permissions import ProjectMember
from dstack._internal.server.services import repos
from dstack._internal.server.utils.routers import (
    get_base_api_additional_responses,
    request_size_exceeded,
)

router = APIRouter(
    prefix="/api/project/{project_name}/repos",
    tags=["repos"],
    responses=get_base_api_additional_responses(),
)


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
    user, project = user_project
    repo = await repos.get_repo(
        session=session,
        project=project,
        user=user,
        repo_id=body.repo_id,
        include_creds=body.include_creds,
    )
    if repo is None:
        raise ResourceNotExistsError()
    return repo


@router.post("/init")
async def init_repo(
    body: SaveRepoCredsRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    """
    Creates or updates a repo with the repo info and repo creds.
    Runs belong to repos, so this endpoint must be called before applying run configurations.
    You can create `virtual` repos if you don't use git repos.
    """
    user, project = user_project
    await repos.init_repo(
        session=session,
        project=project,
        user=user,
        repo_id=body.repo_id,
        repo_info=body.repo_info,
        repo_creds=body.repo_creds,
    )


@router.post("/delete")
async def delete_repos(
    body: DeleteReposRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    _, project = user_project
    await repos.delete_repos(session=session, project=project, repos_ids=body.repos_ids)


@router.post("/upload_code")
async def upload_code(
    request: Request,
    repo_id: str,
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    if request_size_exceeded(request, limit=2 * 2**20):
        raise ServerClientError(
            "Repo diff size exceeds the limit of 2MB. "
            "Use .gitignore to exclude large files from the repo."
        )
    _, project = user_project
    await repos.upload_code(
        session=session,
        project=project,
        repo_id=repo_id,
        file=file,
    )
