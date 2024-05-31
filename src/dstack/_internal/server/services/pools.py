import asyncio
import ipaddress
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

import gpuhunt
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.backends import BACKENDS_WITH_MULTINODE_SUPPORT
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
    InstanceAvailability,
    InstanceOffer,
    InstanceOfferWithAvailability,
    InstanceType,
    RemoteConnectionInfo,
    Resources,
    SSHKey,
)
from dstack._internal.core.models.pools import Instance, Pool, PoolInstances
from dstack._internal.core.models.profiles import DEFAULT_POOL_NAME, Profile, TerminationPolicy
from dstack._internal.core.models.runs import InstanceStatus, JobProvisioningData, Requirements
from dstack._internal.core.models.users import GlobalRole
from dstack._internal.server import settings
from dstack._internal.server.models import InstanceModel, PoolModel, ProjectModel, UserModel
from dstack._internal.server.services.jobs import PROCESSING_POOL_LOCK
from dstack._internal.server.services.projects import list_project_models, list_user_project_models
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


async def get_or_create_pool_by_name(
    session: AsyncSession, project: ProjectModel, pool_name: Optional[str]
) -> PoolModel:
    if pool_name is None:
        if project.default_pool_id is not None:
            return await get_default_pool_or_error(session, project)
        default_pool = await get_pool(session, project, DEFAULT_POOL_NAME)
        if default_pool is not None:
            await set_default_pool(session, project, DEFAULT_POOL_NAME)
            return default_pool
        return await create_pool(session, project, DEFAULT_POOL_NAME)
    pool = await get_pool(session, project, pool_name)
    if pool is not None:
        return pool
    return await create_pool(session, project, pool_name)


async def get_default_pool_or_error(session: AsyncSession, project: ProjectModel) -> PoolModel:
    res = await session.execute(select(PoolModel).where(PoolModel.id == project.default_pool_id))
    return res.scalar_one()


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
    if project.default_pool_id is None:
        await set_default_pool(session, project, pool.name)
    return pool


async def list_project_pool_models(
    session: AsyncSession, project: ProjectModel, select_deleted: bool = False
) -> List[PoolModel]:
    filters = [PoolModel.project_id == project.id]
    if not select_deleted:
        filters.append(PoolModel.deleted == select_deleted)
    pools = await session.execute(
        select(PoolModel).where(*filters).options(joinedload(PoolModel.instances))
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
        if instance.status != InstanceStatus.TERMINATED:
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
    instances = list(map(instance_model_to_instance, pool_instances))
    return PoolInstances(
        name=pool.name,
        instances=instances,
    )


def get_pool_instances(pool: PoolModel) -> List[InstanceModel]:
    return [instance for instance in pool.instances if not instance.deleted]


def instance_model_to_instance(instance_model: InstanceModel) -> Instance:
    instance = Instance(
        id=instance_model.id,
        name=instance_model.name,
        status=instance_model.status,
        unreachable=instance_model.unreachable,
        created=instance_model.created_at.replace(tzinfo=timezone.utc),
    )

    if instance_model.offer is not None:
        offer = InstanceOfferWithAvailability.__response__.parse_raw(instance_model.offer)
        instance.backend = offer.backend
        instance.region = offer.region
        instance.price = offer.price

    if instance_model.job_provisioning_data is not None:
        jpd = JobProvisioningData.__response__.parse_raw(instance_model.job_provisioning_data)
        instance.instance_type = jpd.instance_type
        instance.hostname = jpd.hostname

    if instance_model.job is not None:
        instance.job_name = instance_model.job.job_name
        instance.job_status = instance_model.job.status

    if instance_model.pool is not None:
        instance.pool_name = instance_model.pool.name

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
    project: ProjectModel,
    pool_name: Optional[str],
    instance_name: Optional[str],
    instance_network: Optional[str],
    region: Optional[str],
    host: str,
    port: int,
    ssh_user: str,
    ssh_keys: List[SSHKey],
) -> Instance:
    if instance_network is not None:
        try:
            interface = ipaddress.IPv4Interface(instance_network)
            instance_network = str(interface.network)
        except ipaddress.AddressValueError:
            raise ServerClientError("Failed to parse network value")

    # Check instance in all instances
    pools = await list_project_pool_models(session, project)
    for pool in pools:
        for instance in pool.instances:
            if instance.deleted:
                continue
            if instance.remote_connection_info is not None:
                rci = RemoteConnectionInfo.__response__.parse_raw(instance.remote_connection_info)
                if rci.host == host and rci.port == port and rci.ssh_user == ssh_user:
                    return instance_model_to_instance(instance)

    pool_model = await get_or_create_pool_by_name(session, project, pool_name)
    pool_model_name = pool_model.name
    if instance_name is None:
        instance_name = await generate_instance_name(session, project, pool_model_name)

    # TODO: doc - will overwrite after remote connected
    instance_resource = Resources(cpus=2, memory_mib=8, gpus=[], spot=False)
    instance_type = InstanceType(name="ssh", resources=instance_resource)

    host_region = region if region is not None else "remote"

    remote = JobProvisioningData(
        backend=BackendType.REMOTE,
        instance_type=instance_type,
        instance_id=instance_name,
        hostname=host,
        region=host_region,
        internal_ip=None,
        instance_network=instance_network,
        price=0,
        username=ssh_user,
        ssh_port=port,
        dockerized=True,
        backend_data="",
        ssh_proxy=None,
    )
    offer = InstanceOfferWithAvailability(
        backend=BackendType.REMOTE,
        instance=instance_type,
        region=host_region,
        price=0.0,
        availability=InstanceAvailability.AVAILABLE,
    )

    ssh_connection_info = RemoteConnectionInfo(
        host=host, port=port, ssh_user=ssh_user, ssh_keys=ssh_keys
    ).json()

    im = InstanceModel(
        id=uuid.uuid4(),
        name=instance_name,
        project=project,
        pool=pool_model,
        backend=BackendType.REMOTE,
        created_at=common_utils.get_current_datetime(),
        started_at=common_utils.get_current_datetime(),
        status=InstanceStatus.PENDING,
        unreachable=False,
        job_provisioning_data=remote.json(),
        remote_connection_info=ssh_connection_info,
        offer=offer.json(),
        region=offer.region,
        price=offer.price,
        termination_policy=TerminationPolicy.DONT_DESTROY,
        termination_idle_time=0,
    )
    session.add(im)
    await session.commit()

    instance = instance_model_to_instance(im)
    return instance


def filter_pool_instances(
    pool_instances: List[InstanceModel],
    profile: Profile,
    requirements: Requirements,
    *,
    status: Optional[InstanceStatus] = None,
    multinode: bool = False,
    master_job_provisioning_data: Optional[JobProvisioningData] = None,
) -> List[InstanceModel]:
    """
    Filter instances by `instance_name`, `backends`, `resources`, `spot_policy`, `max_price`, `status`
    """
    instances: List[InstanceModel] = []
    candidates: List[InstanceModel] = []
    for instance in pool_instances:
        if instance.unreachable:
            continue
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

        if profile.regions is not None and instance.region not in profile.regions:
            continue

        if multinode and instance.backend not in BACKENDS_WITH_MULTINODE_SUPPORT:
            continue

        if master_job_provisioning_data is not None and (
            instance.backend != master_job_provisioning_data.backend
            or instance.region != master_job_provisioning_data.region
        ):
            continue

        candidates.append(instance)

    query_filter = requirements_to_query_filter(requirements)
    for instance in candidates:
        if instance.offer is None:
            continue
        offer = InstanceOffer.__response__.parse_raw(instance.offer)
        catalog_item = offer_to_catalog_item(offer)
        if gpuhunt.matches(catalog_item, query_filter):
            instances.append(instance)
    return instances


async def list_pools_instance_models(
    session: AsyncSession,
    projects: List[ProjectModel],
    pools: List[PoolModel],
    only_active: bool,
    prev_created_at: Optional[datetime],
    prev_id: Optional[uuid.UUID],
    limit: int,
    ascending: bool,
) -> List[InstanceModel]:
    filters: List = [
        InstanceModel.project_id.in_(p.id for p in projects),
        InstanceModel.pool_id.in_(p.id for p in pools),
    ]
    if only_active:
        filters.extend(
            [
                InstanceModel.deleted == False,
                InstanceModel.status.in_([InstanceStatus.IDLE, InstanceStatus.BUSY]),
            ]
        )
    if prev_created_at is not None:
        if ascending:
            if prev_id is None:
                filters.append(InstanceModel.created_at > prev_created_at)
            else:
                filters.append(
                    or_(
                        InstanceModel.created_at > prev_created_at,
                        and_(
                            InstanceModel.created_at == prev_created_at,
                            InstanceModel.id < prev_id,
                        ),
                    )
                )
        else:
            if prev_id is None:
                filters.append(InstanceModel.created_at < prev_created_at)
            else:
                filters.append(
                    or_(
                        InstanceModel.created_at < prev_created_at,
                        and_(
                            InstanceModel.created_at == prev_created_at,
                            InstanceModel.id > prev_id,
                        ),
                    )
                )
    order_by = (InstanceModel.created_at.desc(), InstanceModel.id)
    if ascending:
        order_by = (InstanceModel.created_at.asc(), InstanceModel.id.desc())

    res = await session.execute(
        select(InstanceModel)
        .where(*filters)
        .order_by(*order_by)
        .limit(limit)
        .options(joinedload(InstanceModel.pool))
    )
    instance_models = list(res.scalars().all())
    return instance_models


async def list_user_pool_instances(
    session: AsyncSession,
    user: UserModel,
    project_name: Optional[str],
    pool_name: Optional[str],
    only_active: bool,
    prev_created_at: Optional[datetime],
    prev_id: Optional[uuid.UUID],
    limit: int,
    ascending: bool,
) -> List[Instance]:
    if user.global_role == GlobalRole.ADMIN:
        projects = await list_project_models(session=session)
    else:
        projects = await list_user_project_models(session=session, user=user)
    if not projects:
        return []

    if project_name is not None:
        projects = [proj for proj in projects if proj.name == project_name]

    pools = []
    for proj in projects:
        project_pools = await list_project_pool_models(
            session=session, project=proj, select_deleted=(not only_active)
        )
        available_pools = project_pools
        if pool_name is not None:
            available_pools = (pool for pool in project_pools if pool.name == pool_name)
        pools.extend(available_pools)
    if not pools:
        return []

    instance_models = await list_pools_instance_models(
        session=session,
        projects=projects,
        pools=pools,
        only_active=only_active,
        prev_created_at=prev_created_at,
        prev_id=prev_id,
        limit=limit,
        ascending=ascending,
    )
    instances = []
    for instance in instance_models:
        instances.append(instance_model_to_instance(instance))
    return instances
