import asyncio
from datetime import timezone
from typing import List, Optional, Sequence

from pydantic import parse_raw_as
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.models.instances import InstanceOfferWithAvailability
from dstack._internal.core.models.pools import Instance, Pool
from dstack._internal.core.models.profiles import DEFAULT_POOL_NAME
from dstack._internal.core.models.runs import JobProvisioningData
from dstack._internal.server.models import InstanceModel, PoolModel, ProjectModel
from dstack._internal.utils import random_names
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def list_project_pool(session: AsyncSession, project: ProjectModel) -> List[Pool]:
    pools = list(await list_project_pool_models(session=session, project=project))
    if not pools:
        pool = await create_pool_model(session, project, DEFAULT_POOL_NAME)
        pools.append(pool)
    return [pool_model_to_pool(p) for p in pools]


def pool_model_to_pool(pool_model: PoolModel) -> Pool:
    return Pool(
        name=pool_model.name,
        default=pool_model.project.default_pool_id == pool_model.id,
        created_at=pool_model.created_at.replace(tzinfo=timezone.utc),
    )


async def create_pool_model(session: AsyncSession, project: ProjectModel, name: str) -> PoolModel:
    pool = PoolModel(
        name=name,
        project_id=project.id,
    )
    session.add(pool)
    await session.commit()
    project.default_pool = pool  # TODO: add CLI flag --set-default
    await session.commit()
    return pool


async def list_project_pool_models(
    session: AsyncSession, project: ProjectModel
) -> Sequence[PoolModel]:
    pools = await session.scalars(
        select(PoolModel).where(PoolModel.project_id == project.id, PoolModel.deleted == False)
    )
    return pools.all()


async def delete_pool(session: AsyncSession, project: ProjectModel, pool_name: str):
    """delete the pool and set the default pool to project"""

    default_pool: Optional[PoolModel] = None
    default_pool_removed = False

    for pool in await list_project_pool_models(session, project):
        if pool.name == DEFAULT_POOL_NAME:
            default_pool = pool

        if pool_name == pool.name:
            if project.default_pool_id == pool.id:
                default_pool_removed = True
            pool.deleted = True
            pool.deleted_at = get_current_datetime()

    if default_pool_removed:
        if default_pool is not None:
            project.default_pool = default_pool
        else:
            await create_pool_model(session, project, DEFAULT_POOL_NAME)

    await session.commit()


async def list_deleted_pools(
    session: AsyncSession, project_model: ProjectModel
) -> Sequence[PoolModel]:
    pools = await session.scalars(
        select(PoolModel).where(
            PoolModel.project_id == project_model.id, PoolModel.deleted == True
        )
    )
    return pools.all()


def instance_model_to_instance(instance_model: InstanceModel) -> Instance:
    offer: InstanceOfferWithAvailability = parse_raw_as(
        InstanceOfferWithAvailability, instance_model.offer
    )
    jpd: JobProvisioningData = parse_raw_as(
        JobProvisioningData, instance_model.job_provisioning_data
    )

    instance = Instance(
        backend=offer.backend,
        instance_id=jpd.instance_id,
        instance_type=jpd.instance_type,
        hostname=jpd.hostname,
        status=instance_model.status,
        price=offer.price,
    )
    return instance


async def show_pool(
    session: AsyncSession, project: ProjectModel, pool_name: str
) -> Sequence[Instance]:
    pools = (
        await session.scalars(
            select(PoolModel).where(
                PoolModel.name == pool_name, PoolModel.project_id == project.id
            )
        )
    ).all()

    instances = [instance_model_to_instance(i) for i in pools[0].instances]
    return instances


async def get_pool_instances(session: AsyncSession, pool_name: str) -> List[InstanceModel]:
    res = await session.execute(
        select(PoolModel)
        .where(PoolModel.name == pool_name)
        .options(joinedload(PoolModel.instances))
    )
    result = res.unique().scalars().one_or_none()
    if result is None:
        return []
    return result.instances


_GENERATE_POOL_NAME_LOCK = {}


async def generate_instance_name(
    session: AsyncSession,
    project: ProjectModel,
    pool_name: str,
) -> str:
    lock = _GENERATE_POOL_NAME_LOCK.setdefault(project.name, asyncio.Lock())
    async with lock:
        pool_instances: List[InstanceModel] = await get_pool_instances(session, pool_name)
        names = {g.name for g in pool_instances}
        while True:
            name = f"{random_names.generate_name()}"
            if name not in names:
                return name
