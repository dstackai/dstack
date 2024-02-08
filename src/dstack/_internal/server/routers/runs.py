from typing import List, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ResourceNotExistsError, ServerClientError
from dstack._internal.core.models.instances import InstanceOfferWithAvailability
from dstack._internal.core.models.pools import Instance
from dstack._internal.core.models.runs import Run, RunPlan
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
    generate_instance_name,
    get_or_create_default_pool_by_name,
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
    return await runs.list_user_runs(
        session=session,
        user=user,
        project_name=body.project_name,
        repo_id=body.repo_id,
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
        raise ResourceNotExistsError()
    return run


@project_router.post("/get_offers")
async def get_offers(
    body: GetOffersRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> Tuple[str, List[InstanceOfferWithAvailability]]:
    _, project = user_project

    active_pool = await get_or_create_default_pool_by_name(
        session, project, body.profile.pool_name
    )

    offers = await runs.get_run_plan_by_requirements(project, body.profile, body.requirements)
    instances = [instance for _, instance in offers]

    return active_pool.name, instances


@project_router.post("/create_instance")
async def create_instance(
    body: CreateInstanceRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> Instance:
    user, project = user_project
    instance_name = await generate_instance_name(
        session=session, project=project, pool_name=body.pool_name
    )
    instance = await runs.create_instance(
        session=session,
        project=project,
        user=user,
        ssh_key=body.ssh_key,
        pool_name=body.pool_name,
        instance_name=instance_name,
        profile=body.profile,
        requirements=body.requirements,
    )
    if instance is None:
        raise ServerClientError(msg="Failed to create an instance")
    return instance


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
