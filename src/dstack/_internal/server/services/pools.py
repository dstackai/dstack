import asyncio
from datetime import timezone
from typing import Dict, List, Optional

import gpuhunt
from pydantic import parse_raw_as
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.backends.base.offers import (
    offer_to_catalog_item,
    requirements_to_query_filter,
)
from dstack._internal.core.errors import (
    ResourceExistsError,
    ResourceNotExistsError,
    ServerClientError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    Gpu,
    InstanceAvailability,
    InstanceOffer,
    InstanceOfferWithAvailability,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.pools import Instance, Pool, PoolInstances
from dstack._internal.core.models.profiles import DEFAULT_POOL_NAME, Profile
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import InstanceStatus, JobProvisioningData, Requirements
from dstack._internal.server import settings
from dstack._internal.server.models import InstanceModel, PoolModel, ProjectModel
from dstack._internal.server.services.jobs import PROCESSING_POOL_LOCK
from dstack._internal.utils import common as common_utils
from dstack._internal.utils import random_names
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def list_project_pools(session: AsyncSession, project: ProjectModel) -> List[Pool]:
    pools = await list_project_pool_models(session=session, project=project)
    if len(pools) == 0:
        pool = await get_or_create_pool_by_name(session, project, DEFAULT_POOL_NAME)
        pools.append(pool)
    return [pool_model_to_pool(p) for p in pools]


async def get_pool(
    session: AsyncSession, project: ProjectModel, pool_name: str
) -> Optional[PoolModel]:
    res = await session.scalars(
        select(PoolModel).where(
            PoolModel.name == pool_name,
            PoolModel.project_id == project.id,
            PoolModel.deleted == False,
        )
    )
    return res.one_or_none()


async def get_named_or_default_pool(
    session: AsyncSession, project: ProjectModel, pool_name: Optional[str]
) -> Optional[PoolModel]:
    if pool_name is not None:
        return await get_pool(session, project, pool_name)
    return project.default_pool


async def get_or_create_pool_by_name(
    session: AsyncSession, project: ProjectModel, pool_name: Optional[str]
) -> PoolModel:
    if pool_name is None:
        if project.default_pool is not None:
            return project.default_pool
        default_pool = await get_pool(session, project, DEFAULT_POOL_NAME)
        if default_pool is not None:
            await set_default_pool(session, project, DEFAULT_POOL_NAME)
            return default_pool
        return await create_pool(session, project, DEFAULT_POOL_NAME)
    pool = await get_pool(session, project, pool_name)
    if pool is not None:
        return pool
    return await create_pool(session, project, pool_name)


async def create_pool(session: AsyncSession, project: ProjectModel, name: str) -> PoolModel:
    pool = await get_pool(session, project, name)
    if pool is not None:
        raise ResourceExistsError()
    pool = PoolModel(
        name=name,
        project_id=project.id,
    )
    session.add(pool)
    await session.commit()
    await session.refresh(pool)
    if project.default_pool is None:
        await set_default_pool(session, project, pool.name)
    return pool


async def list_project_pool_models(
    session: AsyncSession, project: ProjectModel
) -> List[PoolModel]:
    pools = await session.execute(
        select(PoolModel)
        .where(PoolModel.project_id == project.id, PoolModel.deleted == False)
        .options(joinedload(PoolModel.instances))
    )
    return list(pools.scalars().unique().all())


async def set_default_pool(session: AsyncSession, project: ProjectModel, pool_name: str):
    pool = await get_pool(session, project, pool_name)
    if pool is None:
        raise ResourceNotExistsError("Pool not found")
    project.default_pool = pool
    await session.commit()


async def delete_pool(session: AsyncSession, project: ProjectModel, pool_name: str) -> None:
    # TODO force delete
    pool = await get_pool(session, project, pool_name)
    if pool is None:
        raise ResourceNotExistsError("Pool not found")

    pool_instances = get_pool_instances(pool)
    for instance in pool_instances:
        if not instance.status.is_finished():
            raise ServerClientError("Cannot delete pool with running instances")

    pool.deleted = True
    pool.deleted_at = get_current_datetime()
    if project.default_pool_id == pool.id:
        project.default_pool_id = None
    await session.commit()


def pool_model_to_pool(pool_model: PoolModel) -> Pool:
    total = 0
    available = 0
    for instance in pool_model.instances:
        if not instance.deleted:
            total += 1
            if instance.status.is_available():
                available += 1
    return Pool(
        name=pool_model.name,
        default=pool_model.project.default_pool_id == pool_model.id,
        created_at=pool_model.created_at.replace(tzinfo=timezone.utc),
        total_instances=total,
        available_instances=available,
    )


async def remove_instance(
    session: AsyncSession,
    project: ProjectModel,
    pool_name: str,
    instance_name: str,
    force: bool,
):
    pool = await get_pool(session, project, pool_name)
    if pool is None:
        raise ResourceNotExistsError("Pool not found")
    async with PROCESSING_POOL_LOCK:
        terminated = False
        for instance in pool.instances:
            if instance.name == instance_name:
                if force or instance.job_id is None:
                    instance.status = InstanceStatus.TERMINATING
                    terminated = True
        await session.commit()
    if not terminated:
        raise ResourceNotExistsError("Could not find instance to terminate")


async def show_pool_instances(
    session: AsyncSession, project: ProjectModel, pool_name: Optional[str]
) -> PoolInstances:
    if pool_name is not None:
        pool = await get_pool(session, project, pool_name)
        if pool is None:
            raise ResourceNotExistsError("Pool not found")
    else:
        pool = await get_or_create_pool_by_name(session, project, pool_name)
    pool_instances = get_pool_instances(pool)
    instances = []
    for instance_item in pool_instances:
        instance = instance_model_to_instance(instance_item)
        # TODO: Backward compatibility, will be removed in 0.17
        if instance.status == InstanceStatus.IDLE:
            instance.status = InstanceStatus.READY
        elif instance.status == InstanceStatus.PROVISIONING:
            instance.status = InstanceStatus.STARTING
        instances.append(instance)
    return PoolInstances(
        name=pool.name,
        instances=instances,
    )


def get_pool_instances(pool: PoolModel) -> List[InstanceModel]:
    return [instance for instance in pool.instances if not instance.deleted]


def instance_model_to_instance(instance_model: InstanceModel) -> Instance:
    offer: InstanceOfferWithAvailability = InstanceOfferWithAvailability.parse_raw(
        instance_model.offer
    )
    jpd: JobProvisioningData = JobProvisioningData.parse_raw(instance_model.job_provisioning_data)
    instance = Instance(
        backend=offer.backend,
        name=instance_model.name,
        instance_type=jpd.instance_type,
        hostname=jpd.hostname,
        status=instance_model.status,
        region=offer.region,
        created=instance_model.created_at.replace(tzinfo=timezone.utc),
        price=offer.price,
    )
    if instance_model.job is not None:
        instance.job_name = instance_model.job.job_name
        instance.job_status = instance_model.job.status
    return instance


_GENERATE_POOL_NAME_LOCK: Dict[str, asyncio.Lock] = {}


async def generate_instance_name(
    session: AsyncSession,
    project: ProjectModel,
    pool_name: str,
) -> str:
    lock = _GENERATE_POOL_NAME_LOCK.setdefault(project.name, asyncio.Lock())
    async with lock:
        pool_instances = []
        pool = await get_pool(session, project, pool_name)
        if pool is not None:
            pool_instances = get_pool_instances(pool)
        names = {g.name for g in pool_instances}
        while True:
            name = f"{random_names.generate_name()}"
            if name not in names:
                return name


async def add_remote(
    session: AsyncSession,
    resources: ResourcesSpec,
    project: ProjectModel,
    profile: Profile,
    instance_name: Optional[str],
    host: str,
    port: str,
) -> bool:
    pool_model = await get_or_create_pool_by_name(session, project, profile.pool_name)

    profile.pool_name = pool_model.name
    if instance_name is None:
        instance_name = await generate_instance_name(session, project, profile.pool_name)

    gpus = []
    if resources.gpu is not None:
        gpus = [
            Gpu(name=resources.gpu.name, memory_mib=resources.gpu.memory)
        ] * resources.gpu.count.min

    instance_resource = Resources(
        cpus=resources.cpu.min, memory_mib=resources.memory.min, gpus=gpus, spot=False
    )

    local = JobProvisioningData(
        backend=BackendType.REMOTE,
        instance_type=InstanceType(name="local", resources=instance_resource),
        instance_id=instance_name,
        hostname=host,
        region="",
        price=0,
        username="",
        ssh_port=22,
        dockerized=False,
        backend_data="",
        ssh_proxy=None,
    )
    offer = InstanceOfferWithAvailability(
        backend=BackendType.REMOTE,
        instance=InstanceType(
            name="instance",
            resources=instance_resource,
        ),
        region="",  # TODO: add region
        price=0.0,
        availability=InstanceAvailability.AVAILABLE,
    )

    im = InstanceModel(
        name=instance_name,
        project=project,
        pool=pool_model,
        backend=BackendType.REMOTE,
        created_at=common_utils.get_current_datetime(),
        started_at=common_utils.get_current_datetime(),
        status=InstanceStatus.PENDING,
        job_provisioning_data=local.json(),
        offer=offer.json(),
        region=offer.region,
        price=offer.price,
        termination_policy=profile.termination_policy,
        termination_idle_time=profile.termination_idle_time,
    )
    session.add(im)
    await session.commit()

    return True


def filter_pool_instances(
    pool_instances: List[InstanceModel],
    profile: Profile,
    requirements: Requirements,
    *,
    status: Optional[InstanceStatus] = None,
) -> List[InstanceModel]:
    """
    Filter instances by `instance_name`, `backends`, `resources`, `spot_policy`, `max_price`, `status`
    """
    instances: List[InstanceModel] = []
    candidates: List[InstanceModel] = []
    for instance in pool_instances:
        if profile.instance_name is not None and instance.name != profile.instance_name:
            continue
        if status is not None and instance.status != status:
            continue

        # TODO: remove on prod
        if settings.LOCAL_BACKEND_ENABLED and instance.backend == BackendType.LOCAL:
            instances.append(instance)
            continue

        if profile.backends is not None and instance.backend not in profile.backends:
            continue
        candidates.append(instance)

    query_filter = requirements_to_query_filter(requirements)
    for instance in candidates:
        catalog_item = offer_to_catalog_item(parse_raw_as(InstanceOffer, instance.offer))
        if gpuhunt.matches(catalog_item, query_filter):
            instances.append(instance)
    return instances
