from typing import List, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.core.models.pools as models
import dstack._internal.server.schemas.pools as schemas
import dstack._internal.server.services.pools as pools
from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.pools import Instance
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.pools import ListPoolsRequest
from dstack._internal.server.schemas.runs import AddRemoteInstanceRequest
from dstack._internal.server.security.permissions import Authenticated, ProjectMember

root_router = APIRouter(prefix="/api/pools", tags=["pool"])
router = APIRouter(prefix="/api/project/{project_name}/pool", tags=["pool"])


@root_router.post("/list_instances")
async def list_pool_instances(
    body: ListPoolsRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
) -> List[Instance]:
    """
    Returns all instances visible to user sorted by descending created_at.
    A **project_name** and **pool_name** can be specified as filters.

    The results are paginated. To get the next page, pass created_at and id of
    the last run from the previous page as **prev_created_at** and **prev_id**.
    """
    return await pools.list_user_pool_instances(
        session=session,
        user=user,
        project_name=body.project_name,
        pool_name=body.pool_name,
        only_active=body.only_active,
        prev_created_at=body.prev_created_at,
        prev_id=body.prev_id,
        limit=body.limit,
        ascending=body.ascending,
    )


@router.post("/list")
async def list_pool(
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> List[models.Pool]:
    _, project = user_project
    return await pools.list_project_pools(session=session, project=project)


@router.post("/create")
async def create_pool(
    body: schemas.CreatePoolRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> None:
    _, project = user_project
    await pools.create_pool(session=session, project=project, name=body.name)


@router.post("/set_default")
async def set_default_pool(
    body: schemas.SetDefaultPoolRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    _, project_model = user_project
    await pools.set_default_pool(session, project_model, body.pool_name)


@router.post("/delete")
async def delete_pool(
    body: schemas.DeletePoolRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> None:
    _, project = user_project
    await pools.delete_pool(session, project, body.name)


@router.post("/show")
async def show_pool(
    body: schemas.ShowPoolRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> models.PoolInstances:
    _, project = user_project
    return await pools.show_pool_instances(session, project, pool_name=body.name)


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


@router.post("/add_remote")
async def add_instance(
    body: AddRemoteInstanceRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> Instance:
    if not body.host.strip() or not body.ssh_user.strip() or not body.ssh_keys:
        raise ConfigurationError("Host, user or ssh keys are empty")

    _, project = user_project
    result = await pools.add_remote(
        session,
        project=project,
        pool_name=body.pool_name,
        instance_name=body.instance_name,
        instance_network=body.instance_network,
        region=body.region,
        host=body.host,
        port=body.port or 22,
        ssh_user=body.ssh_user,
        ssh_keys=body.ssh_keys,
    )
    return result
