import asyncio
import uuid
from datetime import timezone
from typing import List, Optional, Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.errors import (
    ForbiddenError,
    ResourceExistsError,
    ServerClientError,
)
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.fleets import (
    Fleet,
    FleetSpec,
    FleetStatus,
    SSHHostParams,
    SSHParams,
)
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.profiles import SpotPolicy
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import Requirements, get_policy_map
from dstack._internal.core.models.users import GlobalRole
from dstack._internal.core.services import validate_dstack_resource_name
from dstack._internal.server.models import (
    FleetModel,
    InstanceModel,
    PoolModel,
    ProjectModel,
    UserModel,
)
from dstack._internal.server.services import pools as pools_services
from dstack._internal.server.services.jobs import (
    PROCESSING_INSTANCES_IDS,
    PROCESSING_INSTANCES_LOCK,
)
from dstack._internal.server.services.projects import get_member, get_member_permissions
from dstack._internal.server.utils.common import wait_to_lock_many
from dstack._internal.utils import random_names
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


PROCESSING_FLEETS_LOCK = asyncio.Lock()
PROCESSING_FLEETS_IDS = set()


async def list_project_fleets(
    session: AsyncSession,
    project: ProjectModel,
    names: Optional[List[str]] = None,
) -> List[Fleet]:
    fleet_models = await list_project_fleet_models(session=session, project=project, names=names)
    return [fleet_model_to_fleet(v) for v in fleet_models]


async def list_project_fleet_models(
    session: AsyncSession,
    project: ProjectModel,
    names: Optional[List[str]] = None,
    include_deleted: bool = False,
) -> List[FleetModel]:
    filters = [
        FleetModel.project_id == project.id,
    ]
    if names is not None:
        filters.append(FleetModel.name.in_(names))
    if not include_deleted:
        filters.append(FleetModel.deleted == False)
    res = await session.execute(
        select(FleetModel).where(*filters).options(joinedload(FleetModel.instances))
    )
    return list(res.unique().scalars().all())


async def get_fleet_by_name(
    session: AsyncSession, project: ProjectModel, name: str
) -> Optional[Fleet]:
    fleet_model = await get_project_fleet_model_by_name(
        session=session, project=project, name=name
    )
    if fleet_model is None:
        return None
    return fleet_model_to_fleet(fleet_model)


async def get_project_fleet_model_by_name(
    session: AsyncSession,
    project: ProjectModel,
    name: str,
    include_deleted: bool = False,
) -> Optional[FleetModel]:
    filters = [
        FleetModel.name == name,
        FleetModel.project_id == project.id,
    ]
    if not include_deleted:
        filters.append(FleetModel.deleted == False)
    res = await session.execute(
        select(FleetModel).where(*filters).options(joinedload(FleetModel.instances))
    )
    return res.unique().scalar_one_or_none()


async def create_fleet(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    spec: FleetSpec,
) -> Fleet:
    _validate_fleet_spec(spec)

    if spec.configuration.ssh_config is not None:
        _check_can_manage_ssh_fleets(user=user, project=project)

    if spec.configuration.name is not None:
        fleet_model = await get_project_fleet_model_by_name(
            session=session,
            project=project,
            name=spec.configuration.name,
        )
        if fleet_model is not None:
            raise ResourceExistsError()
    else:
        spec.configuration.name = await generate_fleet_name(session=session, project=project)

    pool = await pools_services.get_or_create_pool_by_name(
        session=session, project=project, pool_name=None
    )
    fleet_model = FleetModel(
        id=uuid.uuid4(),
        name=spec.configuration.name,
        project=project,
        status=FleetStatus.ACTIVE,
        spec=spec.json(),
        instances=[],
    )
    session.add(fleet_model)
    if spec.configuration.ssh_config is not None:
        for i, host in enumerate(spec.configuration.ssh_config.hosts):
            instances_model = await create_fleet_ssh_instance_model(
                project=project,
                pool=pool,
                spec=spec,
                ssh_params=spec.configuration.ssh_config,
                env=spec.configuration.env,
                instance_num=i,
                host=host,
            )
            fleet_model.instances.append(instances_model)
    else:
        for i in range(_get_fleet_nodes_to_provision(spec)):
            instance_model = await create_fleet_instance_model(
                session=session,
                project=project,
                user=user,
                pool=pool,
                spec=spec,
                instance_num=i,
            )
            fleet_model.instances.append(instance_model)
    await session.commit()
    return fleet_model_to_fleet(fleet_model)


async def create_fleet_instance_model(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    pool: PoolModel,
    spec: FleetSpec,
    instance_num: int,
) -> InstanceModel:
    profile = spec.merged_profile
    requirements = Requirements(
        resources=spec.configuration.resources or ResourcesSpec(),
        max_price=profile.max_price,
        spot=get_policy_map(profile.spot_policy, default=SpotPolicy.AUTO),
    )
    instance_model = await pools_services.create_instance_model(
        session=session,
        project=project,
        user=user,
        pool=pool,
        profile=profile,
        requirements=requirements,
        instance_name=f"{spec.configuration.name}-{instance_num}",
        instance_num=instance_num,
    )
    return instance_model


async def create_fleet_ssh_instance_model(
    project: ProjectModel,
    pool: PoolModel,
    spec: FleetSpec,
    ssh_params: SSHParams,
    env: Env,
    instance_num: int,
    host: Union[SSHHostParams, str],
) -> InstanceModel:
    if isinstance(host, str):
        hostname = host
        ssh_user = ssh_params.user
        ssh_key = ssh_params.ssh_key
        port = ssh_params.port
    else:
        hostname = host.hostname
        ssh_user = host.user or ssh_params.user
        ssh_key = host.ssh_key or ssh_params.ssh_key
        port = host.port or ssh_params.port

    if ssh_user is None or ssh_key is None:
        # This should not be reachable but checked by fleet spec validation
        raise ServerClientError("ssh key or user not specified")

    instance_model = await pools_services.create_ssh_instance_model(
        project=project,
        pool=pool,
        instance_name=f"{spec.configuration.name}-{instance_num}",
        instance_num=instance_num,
        region="remote",
        host=hostname,
        ssh_user=ssh_user,
        ssh_keys=[ssh_key],
        env=env,
        instance_network=ssh_params.network,
        port=port or 22,
    )
    return instance_model


async def delete_fleets(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    names: List[str],
    instance_nums: Optional[List[int]] = None,
):
    res = await session.execute(
        select(FleetModel).where(
            FleetModel.project_id == project.id,
            FleetModel.name.in_(names),
            FleetModel.deleted == False,
        )
    )
    fleet_models = res.scalars().all()
    fleets_ids = sorted([v.id for v in fleet_models])
    logger.info("Deleting fleets: %s", [v.name for v in fleet_models])
    await wait_to_lock_many(PROCESSING_FLEETS_LOCK, PROCESSING_FLEETS_IDS, fleets_ids)
    try:
        # Refetch after lock
        res = await session.execute(
            select(FleetModel)
            .where(
                FleetModel.project_id == project.id,
                FleetModel.name.in_(names),
                FleetModel.deleted == False,
            )
            .options(joinedload(FleetModel.instances))
            .options(joinedload(FleetModel.runs))
            .execution_options(populate_existing=True)
        )
        fleet_models = res.scalars().unique().all()
        fleets = [fleet_model_to_fleet(m) for m in fleet_models]
        for fleet in fleets:
            if fleet.spec.configuration.ssh_config is not None:
                _check_can_manage_ssh_fleets(user=user, project=project)
        for fleet_model in fleet_models:
            await _terminate_fleet_instances(fleet_model=fleet_model, instance_nums=instance_nums)
        # TERMINATING fleets are deleted by process_fleets after instances are terminated
        if instance_nums is None:
            fleet_model.status = FleetStatus.TERMINATING
        await session.commit()
    finally:
        PROCESSING_FLEETS_IDS.difference_update(fleets_ids)


def fleet_model_to_fleet(fleet_model: FleetModel, include_sensitive: bool = False) -> Fleet:
    instances = [
        pools_services.instance_model_to_instance(i)
        for i in fleet_model.instances
        if not i.deleted
    ]
    instances = sorted(instances, key=lambda i: i.instance_num)
    spec = get_fleet_spec(fleet_model)
    if not include_sensitive:
        _remove_fleet_spec_sensitive_info(spec)
    return Fleet(
        name=fleet_model.name,
        project_name=fleet_model.project.name,
        spec=spec,
        created_at=fleet_model.created_at.replace(tzinfo=timezone.utc),
        status=fleet_model.status,
        status_message=fleet_model.status_message,
        instances=instances,
    )


def get_fleet_spec(fleet_model: FleetModel) -> FleetSpec:
    return FleetSpec.__response__.parse_raw(fleet_model.spec)


async def generate_fleet_name(session: AsyncSession, project: ProjectModel) -> str:
    fleet_models = await list_project_fleet_models(session=session, project=project)
    names = {v.name for v in fleet_models}
    while True:
        name = random_names.generate_name()
        if name not in names:
            return name


def is_fleet_in_use(fleet_model: FleetModel, instance_nums: Optional[List[int]] = None) -> bool:
    instances_in_use = [i for i in fleet_model.instances if i.job_id is not None]
    selected_instance_in_use = instances_in_use
    if instance_nums is not None:
        selected_instance_in_use = [i for i in instances_in_use if i.instance_num in instance_nums]
    active_runs = [r for r in fleet_model.runs if not r.status.is_finished()]
    return len(selected_instance_in_use) > 0 or len(instances_in_use) == 0 and len(active_runs) > 0


def is_fleet_empty(fleet_model: FleetModel) -> bool:
    active_instances = [i for i in fleet_model.instances if not i.deleted]
    return len(active_instances) == 0


def _check_can_manage_ssh_fleets(user: UserModel, project: ProjectModel):
    if user.global_role == GlobalRole.ADMIN:
        return
    member = get_member(user=user, project=project)
    if member is None:
        raise ForbiddenError()
    permissions = get_member_permissions(member)
    if permissions.can_manage_ssh_fleets:
        return
    raise ForbiddenError()


def _remove_fleet_spec_sensitive_info(spec: FleetSpec):
    if spec.configuration.ssh_config is not None:
        spec.configuration.ssh_config.ssh_key = None
        for host in spec.configuration.ssh_config.hosts:
            if not isinstance(host, str):
                host.ssh_key = None


def _validate_fleet_spec(spec: FleetSpec):
    if spec.configuration.name is not None:
        validate_dstack_resource_name(spec.configuration.name)
    if spec.configuration.ssh_config is None and spec.configuration.nodes is None:
        raise ServerClientError("No ssh_config or nodes specified")
    if spec.configuration.ssh_config is not None:
        for host in spec.configuration.ssh_config.hosts:
            if isinstance(host, str):
                if spec.configuration.ssh_config.ssh_key is None:
                    raise ServerClientError(f"No ssh key specified for host {host}")
                if spec.configuration.ssh_config.user is None:
                    raise ServerClientError(f"No ssh user specified for host {host}")
            else:
                if spec.configuration.ssh_config.ssh_key is None and host.ssh_key is None:
                    raise ServerClientError(f"No ssh key specified for host {host.hostname}")
                if spec.configuration.ssh_config.user is None and host.user is None:
                    raise ServerClientError(f"No ssh user specified for host {host.hostname}")


def _get_fleet_nodes_to_provision(spec: FleetSpec) -> int:
    if spec.configuration.nodes is None or spec.configuration.nodes.min is None:
        return 0
    return spec.configuration.nodes.min


async def _terminate_fleet_instances(fleet_model: FleetModel, instance_nums: Optional[List[int]]):
    if is_fleet_in_use(fleet_model, instance_nums=instance_nums):
        if instance_nums is not None:
            raise ServerClientError(
                f"Failed to delete fleet {fleet_model.name} instances {instance_nums}. Fleet instances are in use."
            )
        raise ServerClientError(f"Failed to delete fleet {fleet_model.name}. Fleet is in use.")
    instances_ids = sorted([i.id for i in fleet_model.instances])
    await wait_to_lock_many(PROCESSING_INSTANCES_LOCK, PROCESSING_INSTANCES_IDS, instances_ids)
    try:
        for instance in fleet_model.instances:
            if instance_nums is not None and instance.instance_num not in instance_nums:
                continue
            instance.status = InstanceStatus.TERMINATING
    finally:
        PROCESSING_INSTANCES_IDS.difference_update(instances_ids)
