from typing import List, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.runs import Run, RunPlan
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.runs import (
    DeleteRunsRequest,
    GetRunRequest,
    StopRunsRequest,
    SubmitRunRequest,
)
from dstack._internal.server.security.permissions import ProjectMember
from dstack._internal.server.services import runs
from dstack._internal.server.utils.routers import raise_not_found, raise_server_client_error

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
    return await runs.list_runs(session=session, project=project)


@router.post("/get")
async def get_run(
    body: GetRunRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> Run:
    _, project = user_project
    try:
        run = await runs.get_run(
            session=session,
            project=project,
            run_name=body.run_name,
        )
    except ServerClientError as e:
        raise_server_client_error(e)
    if run is None:
        raise_not_found()
    return run


@router.post("/get_plan")
async def get_run_plan(
    body: SubmitRunRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> RunPlan:
    user, project = user_project
    run_plan = await runs.get_run_plan(
        session=session,
        project=project,
        user=user,
        run_spec=body.run_spec,
    )
    return run_plan


@router.post("/submit")
async def submit_run(
    body: SubmitRunRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> Run:
    user, project = user_project
    try:
        return await runs.submit_run(
            session=session,
            user=user,
            project=project,
            run_spec=body.run_spec,
        )
    except ServerClientError as e:
        raise_server_client_error(e)


@router.post("/stop")
async def stop_runs(
    body: StopRunsRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    _, project = user_project
    await runs.stop_runs(
        session=session,
        project=project,
        runs_names=body.runs_names,
        abort=body.abort,
    )


@router.post("/delete")
async def delete_runs(
    body: DeleteRunsRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    _, project = user_project
    try:
        await runs.delete_runs(session=session, project=project, runs_names=body.runs_names)
    except ServerClientError as e:
        raise_server_client_error(e)
