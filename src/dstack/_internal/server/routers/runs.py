from typing import List, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.runs import Run, RunPlan
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.runs import GetRunRequest, SubmitRunRequest
from dstack._internal.server.security.permissions import ProjectMember
from dstack._internal.server.services import runs

router = APIRouter(
    prefix="/api/project/{project_name}/runs",
    tags=["runs"],
)


@router.post("/list")
async def list_runs(
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> List[Run]:
    _, project = user_project


@router.post("/get")
async def get_run(
    body: GetRunRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> Run:
    _, project = user_project


@router.post("/get_plan")
async def get_run_plan(
    body: SubmitRunRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> RunPlan:
    pass


@router.post("/submit")
async def submit_run(
    body: SubmitRunRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> Run:
    user, project = user_project
    run = await runs.submit_run(
        session=session,
        user=user,
        project=project,
        run_spec=body.run_spec,
    )
    return run


@router.post("/stop")
async def stop_runs(project_name: str, body):
    pass


@router.post("/delete")
async def delete_runs(project_name: str, body):
    pass
