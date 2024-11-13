import ipaddress
import uuid
from datetime import datetime, timezone
from typing import List, Optional

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
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.instances import (
    DockerConfig,
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOffer,
    InstanceOfferWithAvailability,
    InstanceStatus,
    InstanceType,
    RemoteConnectionInfo,
    Resources,
    SSHKey,
)
from dstack._internal.core.models.pools import Instance, Pool, PoolInstances
from dstack._internal.core.models.profiles import (
    DEFAULT_POOL_NAME,
    Profile,
    TerminationPolicy,
)
from dstack._internal.core.models.runs import JobProvisioningData, Requirements
from dstack._internal.core.models.users import GlobalRole
from dstack._internal.core.models.volumes import Volume
from dstack._internal.server import settings
from dstack._internal.server.models import (
    FleetModel,
    InstanceModel,
    PoolModel,
    ProjectModel,
    UserModel,
)
from dstack._internal.server.services.docker import parse_image_name
from dstack._internal.server.services.jobs.configurators.base import (
    get_default_image,
    get_default_python_verison,
)
from dstack._internal.server.services.locking import get_locker
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
    session: AsyncSession, project: ProjectModel, pool_name: str, select_deleted: bool = False
) -> Optional[PoolModel]:
    filters = [
        PoolModel.name == pool_name,
        PoolModel.project_id == project.id,
    ]
    if not select_deleted:
        filters.append(PoolModel.deleted == False)
    res = await session.scalars(select(PoolModel).where(*filters))
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
    # This is a buggy function since it doesn't lock instances (and never did correctly).
    # No need to fix it since it's deprecated.
    pool = await get_pool(session, project, pool_name)
    if pool is None:
        raise ResourceNotExistsError("Pool not found")
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
        project_name=instance_model.project.name,
        name=instance_model.name,
        instance_num=instance_model.instance_num,
        status=instance_model.status,
        unreachable=instance_model.unreachable,
        termination_reason=instance_model.termination_reason,
        created=instance_model.created_at.replace(tzinfo=timezone.utc),
    )

    offer = get_instance_offer(instance_model)
    if offer is not None:
        instance.backend = offer.backend
        instance.region = offer.region
        instance.price = offer.price

    jpd = get_instance_provisioning_data(instance_model)
    if jpd is not None:
        instance.instance_type = jpd.instance_type
        instance.hostname = jpd.hostname

    if instance_model.job is not None:
        instance.job_name = instance_model.job.job_name

    return instance


def get_instance_provisioning_data(instance_model: InstanceModel) -> Optional[JobProvisioningData]:
    if instance_model.job_provisioning_data is None:
        return None
    return JobProvisioningData.__response__.parse_raw(instance_model.job_provisioning_data)


def get_instance_offer(instance_model: InstanceModel) -> Optional[InstanceOfferWithAvailability]:
    if instance_model.offer is None:
        return None
    return InstanceOfferWithAvailability.__response__.parse_raw(instance_model.offer)


def get_instance_configuration(instance_model: InstanceModel) -> InstanceConfiguration:
    return InstanceConfiguration.__response__.parse_raw(instance_model.instance_configuration)


def get_instance_profile(instance_model: InstanceModel) -> Profile:
    return Profile.__response__.parse_raw(instance_model.profile)


def get_instance_requirements(instance_model: InstanceModel) -> Requirements:
    return Requirements.__response__.parse_raw(instance_model.requirements)


async def generate_instance_name(
    session: AsyncSession,
    project: ProjectModel,
    pool_name: str,
) -> str:
    # FIXME: The locking is not correct since concurrently commited changes
    # are not visible due to SQLite repeatable reads
    lock, _ = get_locker().get_lockset(f"instance_names_{project.name}")
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
        instance_num=0,
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
    fleet_model: Optional[FleetModel] = None,
    multinode: bool = False,
    master_job_provisioning_data: Optional[JobProvisioningData] = None,
    volumes: Optional[List[List[Volume]]] = None,
) -> List[InstanceModel]:
    instances: List[InstanceModel] = []
    candidates: List[InstanceModel] = []

    backend_types = profile.backends
    regions = profile.regions
    zones = None

    if volumes:
        mount_point_volumes = volumes[0]
        backend_types = [v.configuration.backend for v in mount_point_volumes]
        regions = [v.configuration.region for v in mount_point_volumes]
        volume_zones = [
            v.provisioning_data.availability_zone
            for v in mount_point_volumes
            if v.provisioning_data is not None
        ]
        if volume_zones:
            zones = volume_zones

    if multinode:
        if not backend_types:
            backend_types = BACKENDS_WITH_MULTINODE_SUPPORT
        backend_types = [b for b in backend_types if b in BACKENDS_WITH_MULTINODE_SUPPORT]

    # For multi-node, restrict backend and region.
    # The default behavior is to provision all nodes in the same backend and region.
    if master_job_provisioning_data is not None:
        if not backend_types:
            backend_types = [master_job_provisioning_data.get_base_backend()]
        backend_types = [
            b for b in backend_types if b == master_job_provisioning_data.get_base_backend()
        ]
        if not regions:
            regions = [master_job_provisioning_data.region]
        regions = [r for r in regions if r == master_job_provisioning_data.region]

    for instance in pool_instances:
        if fleet_model is not None and instance.fleet_id != fleet_model.id:
            continue
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

        if backend_types is not None and instance.backend not in backend_types:
            continue

        if regions is not None and instance.region not in regions:
            continue

        jpd = get_instance_provisioning_data(instance)
        if (
            jpd is not None
            and jpd.availability_zone is not None
            and zones is not None
            and jpd.availability_zone not in zones
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
    pool: Optional[PoolModel],
    only_active: bool,
    prev_created_at: Optional[datetime],
    prev_id: Optional[uuid.UUID],
    limit: int,
    ascending: bool,
) -> List[InstanceModel]:
    filters: List = [
        InstanceModel.project_id.in_(p.id for p in projects),
    ]
    if pool is not None:
        filters.append(InstanceModel.pool_id == pool.id)
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

    pool = None
    if project_name is not None:
        projects = [proj for proj in projects if proj.name == project_name]
        if len(projects) == 0:
            return []
        if pool_name is not None:
            pool = await get_pool(
                session=session,
                project=projects[0],
                pool_name=pool_name,
                select_deleted=(not only_active),
            )

    instance_models = await list_pools_instance_models(
        session=session,
        projects=projects,
        pool=pool,
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


async def list_active_remote_instances(
    session: AsyncSession,
) -> List[InstanceModel]:
    filters: List = [InstanceModel.deleted == False, InstanceModel.backend == BackendType.REMOTE]

    res = await session.execute(
        select(InstanceModel).where(*filters).order_by(InstanceModel.created_at.asc())
    )
    instance_models = list(res.scalars().all())
    return instance_models


async def create_instance_model(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    pool: PoolModel,
    profile: Profile,
    requirements: Requirements,
    instance_name: str,
    instance_num: int,
    placement_group_name: Optional[str],
    reservation: Optional[str],
) -> InstanceModel:
    instance = InstanceModel(
        id=uuid.uuid4(),
        name=instance_name,
        instance_num=instance_num,
        project=project,
        pool=pool,
        created_at=common_utils.get_current_datetime(),
        status=InstanceStatus.PENDING,
        unreachable=False,
        profile=profile.json(),
        requirements=requirements.json(),
        instance_configuration=None,
        termination_policy=profile.termination_policy,
        termination_idle_time=profile.termination_idle_time,
    )
    session.add(instance)
    await session.flush()
    project_ssh_key = SSHKey(
        public=project.ssh_public_key.strip(),
        private=project.ssh_private_key.strip(),
    )
    dstack_default_image = parse_image_name(get_default_image(get_default_python_verison()))
    instance_config = InstanceConfiguration(
        project_name=project.name,
        instance_name=instance_name,
        user=user.name,
        instance_id=str(instance.id),
        ssh_keys=[project_ssh_key],
        placement_group_name=placement_group_name,
        reservation=reservation,
        job_docker_config=DockerConfig(
            image=dstack_default_image,
            registry_auth=None,
        ),
    )
    instance.instance_configuration = instance_config.json()
    return instance


async def create_ssh_instance_model(
    project: ProjectModel,
    pool: PoolModel,
    instance_name: str,
    instance_num: int,
    instance_network: Optional[str],
    region: Optional[str],
    host: str,
    port: int,
    ssh_user: str,
    ssh_keys: List[SSHKey],
    env: Env,
) -> InstanceModel:
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
    remote_connection_info = RemoteConnectionInfo(
        host=host,
        port=port,
        ssh_user=ssh_user,
        ssh_keys=ssh_keys,
        env=env,
    )
    im = InstanceModel(
        id=uuid.uuid4(),
        name=instance_name,
        instance_num=instance_num,
        project=project,
        pool=pool,
        backend=BackendType.REMOTE,
        created_at=common_utils.get_current_datetime(),
        started_at=common_utils.get_current_datetime(),
        status=InstanceStatus.PENDING,
        unreachable=False,
        job_provisioning_data=remote.json(),
        remote_connection_info=remote_connection_info.json(),
        offer=offer.json(),
        region=offer.region,
        price=offer.price,
        termination_policy=TerminationPolicy.DONT_DESTROY,
        termination_idle_time=0,
    )
    return im
