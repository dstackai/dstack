from typing import List, Sequence, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.core.models.pools as models
import dstack._internal.server.schemas.pools as schemas
import dstack._internal.server.services.pools as pools
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.runs import AddRemoteInstanceRequest
from dstack._internal.server.security.permissions import ProjectAdmin, ProjectMember
from dstack._internal.server.services.runs import (
    abort_runs_of_pool,
    list_project_runs,
    run_model_to_run,
)

router = APIRouter(prefix="/api/project/{project_name}/pool", tags=["pool"])


@router.post("/list")  # type: ignore[misc]
async def list_pool(
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> List[models.Pool]:
    _, project = user_project
    return await pools.list_project_pool(session=session, project=project)


@router.post("/remove")  # type: ignore[misc]
async def remove_instance(
    body: schemas.RemoveInstanceRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
) -> None:
    _, project_model = user_project
    await pools.remove_instance(session, project_model, body.pool_name, body.instance_name)


@router.post("/set-default")  # type: ignore[misc]
async def set_default_pool(
    body: schemas.SetDefaultPoolRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
) -> bool:
    _, project_model = user_project
    return await pools.set_default_pool(session, project_model, body.pool_name)


@router.post("/delete")  # type: ignore[misc]
async def delete_pool(
    body: schemas.DeletePoolRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
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


@router.post("/create")  # type: ignore[misc]
async def create_pool(
    body: schemas.CreatePoolRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
) -> None:
    _, project = user_project
    await pools.create_pool_model(session=session, project=project, name=body.name)


@router.post("/show")  # type: ignore[misc]
async def how_pool(
    body: schemas.CreatePoolRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
) -> Sequence[models.Instance]:
    _, project = user_project
    return await pools.show_pool(session, project, pool_name=body.name)


@router.post("/add_remote")  # type: ignore[misc]
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
