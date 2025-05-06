import uuid
from collections.abc import Container, Iterable
from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional, Union

import gpuhunt
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.backends import BACKENDS_WITH_MULTINODE_SUPPORT
from dstack._internal.core.backends.base.offers import (
    offer_to_catalog_item,
    requirements_to_query_filter,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.instances import (
    Instance,
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOffer,
    InstanceOfferWithAvailability,
    InstanceStatus,
    InstanceType,
    RemoteConnectionInfo,
    Resources,
    SSHConnectionParams,
    SSHKey,
)
from dstack._internal.core.models.profiles import (
    DEFAULT_FLEET_TERMINATION_IDLE_TIME,
    Profile,
    TerminationPolicy,
)
from dstack._internal.core.models.runs import JobProvisioningData, Requirements
from dstack._internal.core.models.users import GlobalRole
from dstack._internal.core.models.volumes import Volume
from dstack._internal.core.services.profiles import get_termination
from dstack._internal.server.models import (
    FleetModel,
    InstanceModel,
    ProjectModel,
    UserModel,
)
from dstack._internal.server.services.offers import generate_shared_offer
from dstack._internal.server.services.projects import list_project_models, list_user_project_models
from dstack._internal.utils import common as common_utils
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


def instance_model_to_instance(instance_model: InstanceModel) -> Instance:
    instance = Instance(
        id=instance_model.id,
        project_name=instance_model.project.name,
        name=instance_model.name,
        fleet_id=instance_model.fleet_id,
        fleet_name=instance_model.fleet.name if instance_model.fleet else None,
        instance_num=instance_model.instance_num,
        status=instance_model.status,
        unreachable=instance_model.unreachable,
        termination_reason=instance_model.termination_reason,
        created=instance_model.created_at.replace(tzinfo=timezone.utc),
        total_blocks=instance_model.total_blocks,
        busy_blocks=instance_model.busy_blocks,
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
        instance.availability_zone = jpd.availability_zone

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


def get_instance_ssh_private_keys(instance_model: InstanceModel) -> tuple[str, Optional[str]]:
    """
    Returns a pair of SSH private keys: host key and optional proxy jump key.
    """
    host_private_key = instance_model.project.ssh_private_key
    if instance_model.remote_connection_info is None:
        # Cloud instance
        return host_private_key, None
    # SSH instance
    rci = RemoteConnectionInfo.__response__.parse_raw(instance_model.remote_connection_info)
    if rci.ssh_proxy is None:
        return host_private_key, None
    if rci.ssh_proxy_keys is None:
        # Inconsistent RemoteConnectionInfo structure - proxy without keys
        raise ValueError("Missing instance SSH proxy private keys")
    proxy_private_keys = [key.private for key in rci.ssh_proxy_keys if key.private is not None]
    if not proxy_private_keys:
        raise ValueError("No instance SSH proxy private key found")
    return host_private_key, proxy_private_keys[0]


def filter_pool_instances(
    pool_instances: List[InstanceModel],
    profile: Profile,
    *,
    requirements: Optional[Requirements] = None,
    status: Optional[InstanceStatus] = None,
    fleet_model: Optional[FleetModel] = None,
    multinode: bool = False,
    master_job_provisioning_data: Optional[JobProvisioningData] = None,
    volumes: Optional[List[List[Volume]]] = None,
    shared: bool = False,
) -> List[InstanceModel]:
    instances: List[InstanceModel] = []
    candidates: List[InstanceModel] = []

    backend_types = profile.backends
    regions = profile.regions
    zones = profile.availability_zones

    if volumes:
        mount_point_volumes = volumes[0]
        backend_types = [v.configuration.backend for v in mount_point_volumes]
        regions = [v.configuration.region for v in mount_point_volumes]
        volume_zones = [
            v.provisioning_data.availability_zone
            for v in mount_point_volumes
            if v.provisioning_data is not None
        ]
        if zones is None:
            zones = volume_zones
        zones = [z for z in zones if z in volume_zones]

    if multinode:
        if backend_types is None:
            backend_types = BACKENDS_WITH_MULTINODE_SUPPORT
        backend_types = [b for b in backend_types if b in BACKENDS_WITH_MULTINODE_SUPPORT]

    # For multi-node, restrict backend and region.
    # The default behavior is to provision all nodes in the same backend and region.
    if master_job_provisioning_data is not None:
        if backend_types is None:
            backend_types = [master_job_provisioning_data.get_base_backend()]
        backend_types = [
            b for b in backend_types if b == master_job_provisioning_data.get_base_backend()
        ]
        if regions is None:
            regions = [master_job_provisioning_data.region]
        regions = [r for r in regions if r == master_job_provisioning_data.region]

    if regions is not None:
        regions = [r.lower() for r in regions]
    instance_types = profile.instance_types
    if instance_types is not None:
        instance_types = [i.lower() for i in instance_types]

    for instance in pool_instances:
        if fleet_model is not None and instance.fleet_id != fleet_model.id:
            continue
        if instance.unreachable:
            continue
        fleet = instance.fleet
        if profile.fleets is not None and (fleet is None or fleet.name not in profile.fleets):
            continue
        if status is not None and instance.status != status:
            continue
        jpd = get_instance_provisioning_data(instance)
        if jpd is not None:
            if backend_types is not None and jpd.get_base_backend() not in backend_types:
                continue
            if regions is not None and jpd.region.lower() not in regions:
                continue
            if instance_types is not None and jpd.instance_type.name.lower() not in instance_types:
                continue
            if (
                jpd.availability_zone is not None
                and zones is not None
                and jpd.availability_zone not in zones
            ):
                continue
        if instance.total_blocks is None:
            # Still provisioning, we don't know yet if it shared or not
            continue
        if (instance.total_blocks > 1) != shared:
            continue

        candidates.append(instance)

    if requirements is None:
        return candidates

    query_filter = requirements_to_query_filter(requirements)
    for instance in candidates:
        if instance.offer is None:
            continue
        offer = InstanceOffer.__response__.parse_raw(instance.offer)
        catalog_item = offer_to_catalog_item(offer)
        if gpuhunt.matches(catalog_item, query_filter):
            instances.append(instance)
    return instances


def get_shared_pool_instances_with_offers(
    pool_instances: List[InstanceModel],
    profile: Profile,
    requirements: Requirements,
    *,
    idle_only: bool = False,
    fleet_model: Optional[FleetModel] = None,
    volumes: Optional[List[List[Volume]]] = None,
) -> list[tuple[InstanceModel, InstanceOfferWithAvailability]]:
    instances_with_offers: list[tuple[InstanceModel, InstanceOfferWithAvailability]] = []
    query_filter = requirements_to_query_filter(requirements)
    filtered_instances = filter_pool_instances(
        pool_instances=pool_instances,
        profile=profile,
        fleet_model=fleet_model,
        multinode=False,
        volumes=volumes,
        shared=True,
    )
    for instance in filtered_instances:
        if idle_only and instance.status not in [InstanceStatus.IDLE, InstanceStatus.BUSY]:
            continue
        offer = get_instance_offer(instance)
        if offer is None:
            continue
        total_blocks = common_utils.get_or_error(instance.total_blocks)
        idle_blocks = total_blocks - instance.busy_blocks
        for blocks in range(1, total_blocks + 1):
            shared_offer = generate_shared_offer(offer, blocks, total_blocks)
            catalog_item = offer_to_catalog_item(shared_offer)
            if gpuhunt.matches(catalog_item, query_filter):
                if blocks <= idle_blocks:
                    shared_offer.availability = InstanceAvailability.IDLE
                else:
                    shared_offer.availability = InstanceAvailability.BUSY
                if shared_offer.availability == InstanceAvailability.IDLE or not idle_only:
                    instances_with_offers.append((instance, shared_offer))
                break
    return instances_with_offers


async def get_pool_instances(
    session: AsyncSession,
    project: ProjectModel,
) -> List[InstanceModel]:
    res = await session.execute(
        select(InstanceModel)
        .where(
            InstanceModel.project_id == project.id,
            InstanceModel.deleted == False,
        )
        .options(joinedload(InstanceModel.fleet))
    )
    instance_models = list(res.unique().scalars().all())
    return instance_models


async def list_projects_instance_models(
    session: AsyncSession,
    projects: List[ProjectModel],
    fleet_ids: Optional[Iterable[uuid.UUID]],
    only_active: bool,
    prev_created_at: Optional[datetime],
    prev_id: Optional[uuid.UUID],
    limit: int,
    ascending: bool,
) -> List[InstanceModel]:
    filters: List = [
        InstanceModel.project_id.in_(p.id for p in projects),
    ]
    if fleet_ids is not None:
        filters.append(InstanceModel.fleet_id.in_(fleet_ids))
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
        .options(joinedload(InstanceModel.fleet))
    )
    instance_models = list(res.unique().scalars().all())
    return instance_models


async def list_user_instances(
    session: AsyncSession,
    user: UserModel,
    project_names: Optional[Container[str]],
    fleet_ids: Optional[Iterable[uuid.UUID]],
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

    if project_names is not None:
        projects = [proj for proj in projects if proj.name in project_names]
        if len(projects) == 0:
            return []

    instance_models = await list_projects_instance_models(
        session=session,
        projects=projects,
        fleet_ids=fleet_ids,
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
    instance_models = list(res.unique().scalars().all())
    return instance_models


async def create_instance_model(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    profile: Profile,
    requirements: Requirements,
    instance_name: str,
    instance_num: int,
    reservation: Optional[str],
    blocks: Union[Literal["auto"], int],
    tags: Optional[Dict[str, str]],
) -> InstanceModel:
    termination_policy, termination_idle_time = get_termination(
        profile, DEFAULT_FLEET_TERMINATION_IDLE_TIME
    )
    instance_id = uuid.uuid4()
    project_ssh_key = SSHKey(
        public=project.ssh_public_key.strip(),
        private=project.ssh_private_key.strip(),
    )
    instance_config = InstanceConfiguration(
        project_name=project.name,
        instance_name=instance_name,
        user=user.name,
        ssh_keys=[project_ssh_key],
        instance_id=str(instance_id),
        reservation=reservation,
        tags=tags,
    )
    instance = InstanceModel(
        id=instance_id,
        name=instance_name,
        instance_num=instance_num,
        project=project,
        created_at=common_utils.get_current_datetime(),
        status=InstanceStatus.PENDING,
        unreachable=False,
        profile=profile.json(),
        requirements=requirements.json(),
        instance_configuration=instance_config.json(),
        termination_policy=termination_policy,
        termination_idle_time=termination_idle_time,
        total_blocks=None if blocks == "auto" else blocks,
        busy_blocks=0,
    )
    session.add(instance)
    return instance


async def create_ssh_instance_model(
    project: ProjectModel,
    instance_name: str,
    instance_num: int,
    internal_ip: Optional[str],
    instance_network: Optional[str],
    region: Optional[str],
    host: str,
    port: int,
    ssh_user: str,
    ssh_keys: List[SSHKey],
    ssh_proxy: Optional[SSHConnectionParams],
    ssh_proxy_keys: Optional[list[SSHKey]],
    env: Env,
    blocks: Union[Literal["auto"], int],
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
        internal_ip=internal_ip,
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
        ssh_proxy=ssh_proxy,
        ssh_proxy_keys=ssh_proxy_keys,
        env=env,
    )
    im = InstanceModel(
        id=uuid.uuid4(),
        name=instance_name,
        instance_num=instance_num,
        project=project,
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
        total_blocks=None if blocks == "auto" else blocks,
        busy_blocks=0,
    )
    return im
