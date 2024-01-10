from typing import List, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.core.models.pools as models
import dstack._internal.server.schemas.pools as schemas
import dstack._internal.server.services.pools as pools
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.runs import AddInstanceRequest
from dstack._internal.server.security.permissions import ProjectAdmin, ProjectMember
from dstack._internal.server.services.runs import (
    abort_runs_of_pool,
    list_project_runs,
    run_model_to_run,
)

router = APIRouter(prefix="/api/project/{project_name}/pool", tags=["pool"])


@router.post("/list")
async def list_pool(
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> List[models.Pool]:
    _, project = user_project
    return await pools.list_project_pool(session=session, project=project)


@router.post("/delete")
async def delete_pool(
    body: schemas.DeletePoolRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
):
    pool_name = body.name
    _, project_model = user_project

    if body.force:
        await abort_runs_of_pool(session, project_model, pool_name)
        await pools.delete_pool(session, project_model, pool_name)
        return

    # check active runs
    runs = await list_project_runs(session, project_model, repo_id=None)
    active_runs = []
    for run_model in runs:
        if run_model.status.is_finished():
            continue
        run = run_model_to_run(run_model)
        run_pool_name = run.run_spec.profile.pool_name
        if run_pool_name == pool_name:
            active_runs.append(run)
    if active_runs:
        return

    # TODO: check active instances

    await pools.delete_pool(session, project_model, pool_name)


@router.post("/create")
async def create_pool(
    body: schemas.CreatePoolRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
):
    _, project = user_project
    await pools.create_pool_model(session=session, project=project, name=body.name)


@router.post("/show")
async def how_pool(
    body: schemas.CreatePoolRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
):
    _, project = user_project
    return await pools.show_pool(session, project, pool_name=body.name)


@router.post("/add")
async def add_instance(
    body: AddInstanceRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    _, project = user_project
    await pools.add(
        session,
        project,
        pool_name=body.pool_name,
        instance_name=body.instance_name,
        host=body.host,
        port=body.port,
    )
