from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.projects import Project
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.projects import (
    AddProjectMemberRequest,
    CreateProjectRequest,
    DeleteProjectsRequest,
    ListProjectsRequest,
    RemoveProjectMemberRequest,
    SetProjectMembersRequest,
    UpdateProjectRequest,
)
from dstack._internal.server.security.permissions import (
    Authenticated,
    ProjectAdmin,
    ProjectManager,
    ProjectManagerOrPublicProject,
    ProjectManagerOrSelfLeave,
    ProjectMemberOrPublicAccess,
)
from dstack._internal.server.services import fleets, projects
from dstack._internal.server.utils.routers import (
    CustomORJSONResponse,
    get_base_api_additional_responses,
)

router = APIRouter(
    prefix="/api/projects",
    tags=["projects"],
    responses=get_base_api_additional_responses(),
)


@router.post("/list", response_model=List[Project])
async def list_projects(
    body: Optional[ListProjectsRequest] = None,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
):
    """
    Returns projects visible to the user, sorted by ascending `created_at`.

    Returns all accessible projects (member projects for regular users, all non-deleted
    projects for global admins, plus public projects if `include_not_joined` is `True`).

    `members` and `backends` are always empty - call `/api/projects/{project_name}/get` to retrieve them.
    """
    if body is None:
        # For backward compatibility
        body = ListProjectsRequest()
    return CustomORJSONResponse(
        await projects.list_user_accessible_projects(
            session=session, user=user, include_not_joined=body.include_not_joined
        )
    )


@router.post("/list_only_no_fleets", response_model=List[Project])
async def list_only_no_fleets(
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
):
    """
    Returns only projects where the user is a member and that have no active fleets,
    sorted by ascending `created_at`.

    Active fleets are those with `deleted == False`. Projects with deleted fleets
    (but no active fleets) are included.

    `members` and `backends` are always empty - call `/api/projects/{project_name}/get` to retrieve them.
    """
    return CustomORJSONResponse(
        await fleets.list_projects_with_no_active_fleets(session=session, user=user)
    )


@router.post("/create", response_model=Project)
async def create_project(
    body: CreateProjectRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
):
    return CustomORJSONResponse(
        await projects.create_project(
            session=session,
            user=user,
            project_name=body.project_name,
            is_public=body.is_public,
        )
    )


@router.post("/delete")
async def delete_projects(
    body: DeleteProjectsRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
):
    await projects.delete_projects(
        session=session,
        user=user,
        projects_names=body.projects_names,
    )


@router.post("/{project_name}/get", response_model=Project)
async def get_project(
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMemberOrPublicAccess()),
):
    _, project = user_project
    return CustomORJSONResponse(projects.project_model_to_project(project))


@router.post(
    "/{project_name}/set_members",
    response_model=Project,
)
async def set_project_members(
    body: SetProjectMembersRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectManager()),
):
    user, project = user_project
    await projects.set_project_members(
        session=session,
        user=user,
        project=project,
        members=body.members,
    )
    await session.refresh(project)
    return CustomORJSONResponse(projects.project_model_to_project(project))


@router.post(
    "/{project_name}/add_members",
    response_model=Project,
)
async def add_project_members(
    body: AddProjectMemberRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectManagerOrPublicProject()),
):
    user, project = user_project
    await projects.add_project_members(
        session=session,
        user=user,
        project=project,
        members=body.members,
    )
    await session.refresh(project)
    return CustomORJSONResponse(projects.project_model_to_project(project))


@router.post(
    "/{project_name}/remove_members",
    response_model=Project,
)
async def remove_project_members(
    body: RemoveProjectMemberRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectManagerOrSelfLeave()),
):
    user, project = user_project
    await projects.remove_project_members(
        session=session,
        user=user,
        project=project,
        usernames=body.usernames,
    )
    await session.refresh(project)
    return CustomORJSONResponse(projects.project_model_to_project(project))


@router.post(
    "/{project_name}/update",
    response_model=Project,
)
async def update_project(
    body: UpdateProjectRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
):
    user, project = user_project
    await projects.update_project(
        session=session,
        user=user,
        project=project,
        is_public=body.is_public,
    )
    await session.refresh(project)
    return CustomORJSONResponse(projects.project_model_to_project(project))
