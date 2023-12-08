from datetime import timezone
from typing import List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.pool import Pool
from dstack._internal.core.models.profiles import DEFAULT_POOL_NAME
from dstack._internal.server.models import InstanceModel, PoolModel, ProjectModel
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def list_project_pool(session: AsyncSession, project: ProjectModel) -> List[Pool]:
    pools = list(await list_project_pool_models(session=session, project=project))
    if not pools:
        pool = await create_pool_model(DEFAULT_POOL_NAME, session, project)
        pools.append(pool)
    return [pool_model_to_pool(p) for p in pools]


def pool_model_to_pool(pool_model: PoolModel) -> Pool:
    return Pool(
        name=pool_model.name,
        default=pool_model.project.default_pool_id == pool_model.id,
        created_at=pool_model.created_at.replace(tzinfo=timezone.utc),
    )


async def create_pool_model(name: str, session: AsyncSession, project: ProjectModel) -> PoolModel:
    pool = PoolModel(
        name=name,
        project_id=project.id,
    )
    session.add(pool)
    await session.commit()
    project.default_pool = pool
    await session.commit()
    return pool


async def list_project_pool_models(
    session: AsyncSession, project: ProjectModel
) -> Sequence[PoolModel]:
    pools = await session.execute(select(PoolModel).where(PoolModel.project_id == project.id))
    return pools.scalars().all()


async def delete_pool(session: AsyncSession, project: ProjectModel, pool_name: str):
    """delete the pool and set the default pool to project"""

    default_pool: Optional[PoolModel] = None
    default_pool_removed = False

    for pool in await list_project_pool_models(session=session, project=project):
        if pool.name == DEFAULT_POOL_NAME:
            default_pool = pool

        if pool_name == pool.name:
            if project.default_pool_id == pool.id:
                default_pool_removed = True
            await session.delete(pool)

    if default_pool_removed:
        if default_pool is not None:
            project.default_pool = default_pool
        else:
            await create_pool_model(DEFAULT_POOL_NAME, session, project)

    await session.commit()


async def show_pool(
    pool_name: str, session: AsyncSession, project: ProjectModel
) -> Sequence[InstanceModel]:
    pools_result = await session.execute(select(PoolModel).where(PoolModel.name == pool_name))
    pools = pools_result.scalars().all()

    instances = pools[0].instances
    return instances
