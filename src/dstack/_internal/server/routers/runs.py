from typing import List, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ComputeError, ResourceNotExistsError, ServerClientError
from dstack._internal.core.models.pools import Instance
from dstack._internal.core.models.runs import PoolInstanceOffers, Run, RunPlan
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.runs import (
    CreateInstanceRequest,
    DeleteRunsRequest,
    GetOffersRequest,
    GetRunPlanRequest,
    GetRunRequest,
    ListRunsRequest,
    StopRunsRequest,
    SubmitRunRequest,
)
from dstack._internal.server.security.permissions import Authenticated, ProjectMember
from dstack._internal.server.services import runs
from dstack._internal.server.services.pools import (
    get_or_create_pool_by_name,
)

root_router = APIRouter(
    prefix="/api/runs",
    tags=["runs"],
)
project_router = APIRouter(
    prefix="/api/project/{project_name}/runs",
    tags=["runs"],
)


@root_router.post("/list")
async def list_runs(
    body: ListRunsRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
) -> List[Run]:
    """
    Returns all runs visible to user sorted by descending submitted_at.
    A **project_name**, **repo_id**, and **username** can be specified as filters.
    Specifying **repo_id** without **project_name** returns no runs.

    The results are paginated. To get the next page, pass submitted_at and id of
    the last run from the previous page as **prev_submitted_at** and **prev_run_id**.
    """
    return await runs.list_user_runs(
        session=session,
        user=user,
        project_name=body.project_name,
        repo_id=body.repo_id,
        username=body.username,
        only_active=body.only_active,
        prev_submitted_at=body.prev_submitted_at,
        prev_run_id=body.prev_run_id,
        limit=body.limit,
        ascending=body.ascending,
    )


@project_router.post("/get")
async def get_run(
    body: GetRunRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> Run:
    _, project = user_project
    run = await runs.get_run(
        session=session,
        project=project,
        run_name=body.run_name,
    )
    if run is None:
        raise ResourceNotExistsError("Run not found")
    return run


@project_router.post("/get_plan")
async def get_run_plan(
    body: GetRunPlanRequest,
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


@project_router.post("/submit")
async def submit_run(
    body: SubmitRunRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> Run:
    user, project = user_project
    return await runs.submit_run(
        session=session,
        user=user,
        project=project,
        run_spec=body.run_spec,
    )


@project_router.post("/stop")
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


@project_router.post("/delete")
async def delete_runs(
    body: DeleteRunsRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    _, project = user_project
    await runs.delete_runs(session=session, project=project, runs_names=body.runs_names)


# FIXME: get_offers and create_instance semantically belong to pools, not runs
@project_router.post("/get_offers")
async def get_offers(
    body: GetOffersRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> PoolInstanceOffers:
    _, project = user_project
    pool = await get_or_create_pool_by_name(session, project, body.profile.pool_name)
    offers = await runs.get_create_instance_offers(
        project=project,
        profile=body.profile,
        requirements=body.requirements,
    )
    instances = [instance for _, instance in offers]
    return PoolInstanceOffers(pool_name=pool.name, instances=instances)


# FIXME: get_offers and create_instance semantically belong to pools, not runs
@project_router.post("/create_instance")
async def create_instance(
    body: CreateInstanceRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> Instance:
    user, project = user_project
    try:
        instance = await runs.create_instance(
            session=session,
            project=project,
            user=user,
            profile=body.profile,
            requirements=body.requirements,
        )
    except ComputeError as e:
        raise ServerClientError(str(e))
    return instance
