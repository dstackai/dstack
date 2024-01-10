import asyncio
from datetime import timezone
from typing import List, Optional, Sequence

from pydantic import parse_raw_as
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.pools import Instance, Pool
from dstack._internal.core.models.profiles import DEFAULT_POOL_NAME
from dstack._internal.core.models.runs import InstanceStatus, JobProvisioningData
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
    pool = (
        await session.scalars(
            select(PoolModel).where(
                PoolModel.name == pool_name,
                PoolModel.project_id == project.id,
                PoolModel.deleted == False,
            )
        )
    ).one_or_none()
    if pool is not None:
        instances = [instance_model_to_instance(i) for i in pool.instances]
        return instances
    else:
        return []


async def get_pool_instances(
    session: AsyncSession, project: ProjectModel, pool_name: str
) -> List[InstanceModel]:
    res = await session.execute(
        select(PoolModel)
        .where(
            PoolModel.name == pool_name,
            PoolModel.project_id == project.id,
            PoolModel.deleted == False,
        )
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
        pool_instances: List[InstanceModel] = await get_pool_instances(session, project, pool_name)
        names = {g.name for g in pool_instances}
        while True:
            name = f"{random_names.generate_name()}"
            if name not in names:
                return name


async def add(
    session: AsyncSession,
    project: ProjectModel,
    pool_name: str,
    instance_name: Optional[str],
    host: str,
    port: str,
):

    instance_name = instance_name
    if instance_name is None:
        instance_name = await generate_instance_name(session, project, pool_name)

    pool = (
        await session.scalars(
            select(PoolModel).where(
                PoolModel.name == pool_name,
                PoolModel.project_id == project.id,
                PoolModel.deleted == False,
            )
        )
    ).one_or_none()

    if pool is None:
        pool = await create_pool_model(session, project, pool_name)

    local = JobProvisioningData(
        backend=BackendType.LOCAL,
        instance_type=InstanceType(
            name="local", resources=Resources(cpus=0, memory_mib=0, gpus=[], spot=False)
        ),
        instance_id=instance_name,
        hostname=host,
        region="",
        price=0,
        username="",
        ssh_port=22,
        dockerized=False,
        backend_data="",
    )
    offer = InstanceOfferWithAvailability(
        backend=BackendType.LOCAL,
        instance=InstanceType(
            name="instance",
            resources=Resources(cpus=1, memory_mib=512, spot=False, gpus=[]),
        ),
        region="",
        price=0.0,
        availability=InstanceAvailability.AVAILABLE,
    )

    im = InstanceModel(
        name=instance_name,
        project=project,
        pool=pool,
        status=InstanceStatus.PENDING,
        job_provisioning_data=local.json(),
        offer=offer.json(),
    )
    session.add(im)
    await session.commit()
