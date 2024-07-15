import asyncio
import uuid
from datetime import timezone
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.errors import (
    ResourceExistsError,
    ServerClientError,
)
from dstack._internal.core.models.fleets import (
    Fleet,
    FleetSpec,
    FleetStatus,
)
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.profiles import SpotPolicy
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import Requirements, get_policy_map
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
from dstack._internal.server.utils.common import wait_to_lock_many
from dstack._internal.utils import common, random_names
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
    if spec.configuration.ssh is not None:
        instances_models = await create_fleet_ssh_instance_models(
            session=session,
            project=project,
            user=user,
            pool=pool,
            fleet_spec=spec,
        )
        fleet_model.instances.extend(instances_models)
    else:
        # TODO: require min nodes?
        for i in range(spec.configuration.nodes.min):
            instance_model = await create_fleet_instance_model(
                session=session,
                project=project,
                user=user,
                pool=pool,
                fleet_spec=spec,
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
    fleet_spec: FleetSpec,
    instance_num: int,
) -> InstanceModel:
    profile = fleet_spec.merged_profile
    requirements = Requirements(
        resources=fleet_spec.configuration.resources or ResourcesSpec(),
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
        instance_name=f"{fleet_spec.configuration.name}-{instance_num}",
    )
    return instance_model


async def create_fleet_ssh_instance_models(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    pool: PoolModel,
    fleet_spec: FleetSpec,
) -> List[InstanceModel]:
    instances_models = []
    for i, host in enumerate(fleet_spec.configuration.ssh.hosts):
        if isinstance(host, str):
            hostname = host
            ssh_user = fleet_spec.configuration.ssh.user
            ssh_key = fleet_spec.configuration.ssh.ssh_key
            port = fleet_spec.configuration.ssh.port
        else:
            hostname = host.hostname
            ssh_user = host.user or fleet_spec.configuration.ssh.user
            ssh_key = host.ssh_key or fleet_spec.configuration.ssh.ssh_key
            port = host.port or fleet_spec.configuration.ssh.port

        im = await pools_services.create_ssh_instance_model(
            session=session,
            project=project,
            pool=pool,
            instance_name=f"{fleet_spec.configuration.name}-{i}",
            region="remote",
            host=hostname,
            ssh_user=ssh_user,
            ssh_keys=[ssh_key],
            instance_network=None,
            port=port or 22,
        )
        instances_models.append(im)
    return instances_models


async def delete_fleets(session: AsyncSession, project: ProjectModel, names: List[str]):
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
        for fleet_model in fleet_models:
            # TODO: deleted fleets have instances terminating.
            # Consider deleting fleets only after all instanes are terminated.
            await _terminate_fleet_instances(fleet_model=fleet_model)
        await session.execute(
            update(FleetModel)
            .where(
                FleetModel.project_id == project.id,
                FleetModel.id.in_(fleets_ids),
            )
            .values(
                deleted=True,
                deleted_at=common.get_current_datetime(),
            )
        )
        await session.commit()
    finally:
        PROCESSING_FLEETS_IDS.difference_update(fleets_ids)


def fleet_model_to_fleet(fleet_model: FleetModel) -> Fleet:
    instances = [pools_services.instance_model_to_instance(i) for i in fleet_model.instances]
    spec = get_fleet_spec(fleet_model)
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


def is_fleet_in_use(fleet_model: FleetModel) -> bool:
    instances_in_use = [i for i in fleet_model.instances if i.job_id is not None]
    active_runs = [r for r in fleet_model.runs if not r.status.is_finished()]
    return len(instances_in_use) > 0 or len(active_runs) > 0


def is_fleet_empty(fleet_model: FleetModel) -> bool:
    active_instances = [i for i in fleet_model.instances if not i.deleted]
    return len(active_instances) == 0


def _validate_fleet_spec(spec: FleetSpec):
    if spec.configuration.name is not None:
        validate_dstack_resource_name(spec.configuration.name)
    # TODO validate ssh params


async def _terminate_fleet_instances(fleet_model: FleetModel):
    if is_fleet_in_use(fleet_model):
        raise ServerClientError(f"Failed to delete fleet {fleet_model.name}. Fleet is in use.")
    instances_ids = sorted([i.id for i in fleet_model.instances])
    await wait_to_lock_many(PROCESSING_INSTANCES_LOCK, PROCESSING_INSTANCES_IDS, instances_ids)
    try:
        for instance in fleet_model.instances:
            instance.status = InstanceStatus.TERMINATING
    finally:
        PROCESSING_INSTANCES_IDS.difference_update(instances_ids)
