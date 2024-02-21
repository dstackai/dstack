from typing import List, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.core.models.pools as models
import dstack._internal.server.schemas.pools as schemas
import dstack._internal.server.services.pools as pools
from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.runs import AddRemoteInstanceRequest
from dstack._internal.server.security.permissions import ProjectMember
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


@router.post("/remove")
async def remove_instance(
    body: schemas.RemoveInstanceRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> None:
    _, project_model = user_project
    await pools.remove_instance(
        session, project_model, body.pool_name, body.instance_name, body.force
    )


@router.post("/set_default")
async def set_default_pool(
    body: schemas.SetDefaultPoolRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> bool:
    _, project_model = user_project
    return await pools.set_default_pool(session, project_model, body.pool_name)


@router.post("/delete")
async def delete_pool(
    body: schemas.DeletePoolRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> None:
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
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> None:
    _, project = user_project
    await pools.create_pool_model(session=session, project=project, name=body.name)


@router.post("/show")
async def show_pool(
    body: schemas.ShowPoolRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> models.PoolInstances:
    _, project = user_project
    instances = await pools.show_pool(session, project, pool_name=body.name)
    if instances is None:
        raise ResourceNotExistsError("Pool is not found")
    return instances


@router.post("/add_remote")
async def add_instance(
    body: AddRemoteInstanceRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> bool:
    _, project = user_project
    result = await pools.add_remote(
        session,
        project=project,
        resources=body.resources,
        profile=body.profile,
        instance_name=body.instance_name,
        host=body.host,
        port=body.port,
    )
    return result
