import uuid
from collections.abc import Callable
from datetime import datetime
from functools import wraps
from typing import List, Literal, Optional, Tuple, TypeVar, Union, cast

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.features import BACKENDS_WITH_CREATE_INSTANCE_SUPPORT
from dstack._internal.core.errors import (
    ForbiddenError,
    ResourceExistsError,
    ServerClientError,
)
from dstack._internal.core.models.common import ApplyAction, CoreModel
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.fleets import (
    ApplyFleetPlanInput,
    Fleet,
    FleetConfiguration,
    FleetPlan,
    FleetSpec,
    FleetStatus,
    InstanceGroupPlacement,
    SSHHostParams,
    SSHParams,
)
from dstack._internal.core.models.instances import (
    InstanceOfferWithAvailability,
    InstanceStatus,
    RemoteConnectionInfo,
    SSHConnectionParams,
    SSHKey,
)
from dstack._internal.core.models.placement import PlacementGroup
from dstack._internal.core.models.profiles import (
    Profile,
    SpotPolicy,
)
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import Requirements, get_policy_map
from dstack._internal.core.models.users import GlobalRole
from dstack._internal.core.services import validate_dstack_resource_name
from dstack._internal.core.services.diff import ModelDiff, copy_model, diff_models
from dstack._internal.server.db import get_db
from dstack._internal.server.models import (
    FleetModel,
    InstanceModel,
    JobModel,
    ProjectModel,
    UserModel,
)
from dstack._internal.server.services import instances as instances_services
from dstack._internal.server.services import offers as offers_services
from dstack._internal.server.services.instances import (
    get_instance_remote_connection_info,
    list_active_remote_instances,
)
from dstack._internal.server.services.locking import (
    get_locker,
    string_to_lock_id,
)
from dstack._internal.server.services.plugins import apply_plugin_policies
from dstack._internal.server.services.projects import (
    get_member,
    get_member_permissions,
    list_user_project_models,
)
from dstack._internal.server.services.resources import set_resources_defaults
from dstack._internal.utils import random_names
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.ssh import pkey_from_str

logger = get_logger(__name__)


async def list_fleets(
    session: AsyncSession,
    user: UserModel,
    project_name: Optional[str],
    only_active: bool,
    prev_created_at: Optional[datetime],
    prev_id: Optional[uuid.UUID],
    limit: int,
    ascending: bool,
) -> List[Fleet]:
    projects = await list_user_project_models(
        session=session,
        user=user,
        only_names=True,
    )
    if project_name is not None:
        projects = [p for p in projects if p.name == project_name]
    fleet_models = await list_projects_fleet_models(
        session=session,
        projects=projects,
        only_active=only_active,
        prev_created_at=prev_created_at,
        prev_id=prev_id,
        limit=limit,
        ascending=ascending,
    )
    return [
        fleet_model_to_fleet(v, include_deleted_instances=not only_active) for v in fleet_models
    ]


async def list_projects_fleet_models(
    session: AsyncSession,
    projects: List[ProjectModel],
    only_active: bool,
    prev_created_at: Optional[datetime],
    prev_id: Optional[uuid.UUID],
    limit: int,
    ascending: bool,
) -> List[FleetModel]:
    filters = []
    filters.append(FleetModel.project_id.in_(p.id for p in projects))
    if only_active:
        filters.append(FleetModel.deleted == False)
    if prev_created_at is not None:
        if ascending:
            if prev_id is None:
                filters.append(FleetModel.created_at > prev_created_at)
            else:
                filters.append(
                    or_(
                        FleetModel.created_at > prev_created_at,
                        and_(FleetModel.created_at == prev_created_at, FleetModel.id < prev_id),
                    )
                )
        else:
            if prev_id is None:
                filters.append(FleetModel.created_at < prev_created_at)
            else:
                filters.append(
                    or_(
                        FleetModel.created_at < prev_created_at,
                        and_(FleetModel.created_at == prev_created_at, FleetModel.id > prev_id),
                    )
                )
    order_by = (FleetModel.created_at.desc(), FleetModel.id)
    if ascending:
        order_by = (FleetModel.created_at.asc(), FleetModel.id.desc())
    res = await session.execute(
        select(FleetModel)
        .where(*filters)
        .order_by(*order_by)
        .limit(limit)
        .options(joinedload(FleetModel.instances))
    )
    fleet_models = list(res.unique().scalars().all())
    return fleet_models


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


async def get_fleet(
    session: AsyncSession,
    project: ProjectModel,
    name: Optional[str] = None,
    fleet_id: Optional[uuid.UUID] = None,
    include_sensitive: bool = False,
) -> Optional[Fleet]:
    if fleet_id is not None:
        fleet_model = await get_project_fleet_model_by_id(
            session=session, project=project, fleet_id=fleet_id
        )
    elif name is not None:
        fleet_model = await get_project_fleet_model_by_name(
            session=session, project=project, name=name
        )
    else:
        raise ServerClientError("name or id must be specified")
    if fleet_model is None:
        return None
    return fleet_model_to_fleet(fleet_model, include_sensitive=include_sensitive)


async def get_project_fleet_model_by_id(
    session: AsyncSession,
    project: ProjectModel,
    fleet_id: uuid.UUID,
) -> Optional[FleetModel]:
    filters = [
        FleetModel.id == fleet_id,
        FleetModel.project_id == project.id,
    ]
    res = await session.execute(
        select(FleetModel).where(*filters).options(joinedload(FleetModel.instances))
    )
    return res.unique().scalar_one_or_none()


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


async def get_plan(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    spec: FleetSpec,
) -> FleetPlan:
    # Spec must be copied by parsing to calculate merged_profile
    effective_spec = copy_model(spec)
    effective_spec = await apply_plugin_policies(
        user=user.name,
        project=project.name,
        spec=effective_spec,
    )
    # Spec must be copied by parsing to calculate merged_profile
    effective_spec = copy_model(effective_spec)
    _validate_fleet_spec_and_set_defaults(effective_spec)

    action = ApplyAction.CREATE
    current_fleet: Optional[Fleet] = None
    current_fleet_id: Optional[uuid.UUID] = None

    if effective_spec.configuration.name is not None:
        current_fleet = await get_fleet(
            session=session,
            project=project,
            name=effective_spec.configuration.name,
            include_sensitive=True,
        )
        if current_fleet is not None:
            _set_fleet_spec_defaults(current_fleet.spec)
            if _can_update_fleet_spec(current_fleet.spec, effective_spec):
                action = ApplyAction.UPDATE
            current_fleet_id = current_fleet.id
    await _check_ssh_hosts_not_yet_added(session, effective_spec, current_fleet_id)

    offers = []
    if effective_spec.configuration.ssh_config is None:
        offers_with_backends = await get_create_instance_offers(
            project=project,
            profile=effective_spec.merged_profile,
            requirements=get_fleet_requirements(effective_spec),
            fleet_spec=effective_spec,
            blocks=effective_spec.configuration.blocks,
        )
        offers = [offer for _, offer in offers_with_backends]

    _remove_fleet_spec_sensitive_info(effective_spec)
    if current_fleet is not None:
        _remove_fleet_spec_sensitive_info(current_fleet.spec)
    plan = FleetPlan(
        project_name=project.name,
        user=user.name,
        spec=spec,
        effective_spec=effective_spec,
        current_resource=current_fleet,
        offers=offers[:50],
        total_offers=len(offers),
        max_offer_price=max((offer.price for offer in offers), default=None),
        action=action,
    )
    return plan


async def get_create_instance_offers(
    project: ProjectModel,
    profile: Profile,
    requirements: Requirements,
    placement_group: Optional[PlacementGroup] = None,
    fleet_spec: Optional[FleetSpec] = None,
    fleet_model: Optional[FleetModel] = None,
    blocks: Union[int, Literal["auto"]] = 1,
    exclude_not_available: bool = False,
) -> List[Tuple[Backend, InstanceOfferWithAvailability]]:
    multinode = False
    master_job_provisioning_data = None
    if fleet_spec is not None:
        multinode = fleet_spec.configuration.placement == InstanceGroupPlacement.CLUSTER
    if fleet_model is not None:
        fleet = fleet_model_to_fleet(fleet_model)
        multinode = fleet.spec.configuration.placement == InstanceGroupPlacement.CLUSTER
        for instance in fleet_model.instances:
            jpd = instances_services.get_instance_provisioning_data(instance)
            if jpd is not None:
                master_job_provisioning_data = jpd
                break

    offers = await offers_services.get_offers_by_requirements(
        project=project,
        profile=profile,
        requirements=requirements,
        exclude_not_available=exclude_not_available,
        multinode=multinode,
        master_job_provisioning_data=master_job_provisioning_data,
        placement_group=placement_group,
        blocks=blocks,
    )
    offers = [
        (backend, offer)
        for backend, offer in offers
        if offer.backend in BACKENDS_WITH_CREATE_INSTANCE_SUPPORT
    ]
    return offers


async def apply_plan(
    session: AsyncSession,
    user: UserModel,
    project: ProjectModel,
    plan: ApplyFleetPlanInput,
    force: bool,
) -> Fleet:
    spec = await apply_plugin_policies(
        user=user.name,
        project=project.name,
        spec=plan.spec,
    )
    # Spec must be copied by parsing to calculate merged_profile
    spec = copy_model(spec)
    _validate_fleet_spec_and_set_defaults(spec)

    if spec.configuration.ssh_config is not None:
        _check_can_manage_ssh_fleets(user=user, project=project)

    configuration = spec.configuration
    if configuration.name is None:
        return await _create_fleet(
            session=session,
            project=project,
            user=user,
            spec=spec,
        )

    fleet_model = await get_project_fleet_model_by_name(
        session=session,
        project=project,
        name=configuration.name,
    )
    if fleet_model is None:
        return await _create_fleet(
            session=session,
            project=project,
            user=user,
            spec=spec,
        )

    instances_ids = sorted(i.id for i in fleet_model.instances if not i.deleted)
    await session.commit()
    async with (
        get_locker(get_db().dialect_name).lock_ctx(FleetModel.__tablename__, [fleet_model.id]),
        get_locker(get_db().dialect_name).lock_ctx(InstanceModel.__tablename__, instances_ids),
    ):
        # Refetch after lock
        # TODO: Lock instances with FOR UPDATE?
        res = await session.execute(
            select(FleetModel)
            .where(
                FleetModel.project_id == project.id,
                FleetModel.id == fleet_model.id,
                FleetModel.deleted == False,
            )
            .options(
                selectinload(FleetModel.instances)
                .joinedload(InstanceModel.jobs)
                .load_only(JobModel.id)
            )
            .options(selectinload(FleetModel.runs))
            .execution_options(populate_existing=True)
            .order_by(FleetModel.id)  # take locks in order
            .with_for_update(key_share=True)
        )
        fleet_model = res.scalars().unique().one_or_none()
        if fleet_model is not None:
            return await _update_fleet(
                session=session,
                project=project,
                spec=spec,
                current_resource=plan.current_resource,
                force=force,
                fleet_model=fleet_model,
            )

    return await _create_fleet(
        session=session,
        project=project,
        user=user,
        spec=spec,
    )


async def create_fleet(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    spec: FleetSpec,
) -> Fleet:
    spec = await apply_plugin_policies(
        user=user.name,
        project=project.name,
        spec=spec,
    )
    # Spec must be copied by parsing to calculate merged_profile
    spec = copy_model(spec)
    _validate_fleet_spec_and_set_defaults(spec)

    if spec.configuration.ssh_config is not None:
        _check_can_manage_ssh_fleets(user=user, project=project)

    return await _create_fleet(session=session, project=project, user=user, spec=spec)


async def create_fleet_instance_model(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    spec: FleetSpec,
    reservation: Optional[str],
    instance_num: int,
) -> InstanceModel:
    profile = spec.merged_profile
    requirements = get_fleet_requirements(spec)
    instance_model = await instances_services.create_instance_model(
        session=session,
        project=project,
        user=user,
        profile=profile,
        requirements=requirements,
        instance_name=f"{spec.configuration.name}-{instance_num}",
        instance_num=instance_num,
        reservation=reservation,
        blocks=spec.configuration.blocks,
        tags=spec.configuration.tags,
    )
    return instance_model


async def create_fleet_ssh_instance_model(
    project: ProjectModel,
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
        proxy_jump = ssh_params.proxy_jump
        internal_ip = None
        blocks = 1
    else:
        hostname = host.hostname
        ssh_user = host.user or ssh_params.user
        ssh_key = host.ssh_key or ssh_params.ssh_key
        port = host.port or ssh_params.port
        proxy_jump = host.proxy_jump or ssh_params.proxy_jump
        internal_ip = host.internal_ip
        blocks = host.blocks

    if ssh_user is None or ssh_key is None:
        # This should not be reachable but checked by fleet spec validation
        raise ServerClientError("ssh key or user not specified")

    if proxy_jump is not None:
        assert proxy_jump.ssh_key is not None
        ssh_proxy = SSHConnectionParams(
            hostname=proxy_jump.hostname,
            port=proxy_jump.port or 22,
            username=proxy_jump.user,
        )
        ssh_proxy_keys = [proxy_jump.ssh_key]
    else:
        ssh_proxy = None
        ssh_proxy_keys = None

    instance_model = await instances_services.create_ssh_instance_model(
        project=project,
        instance_name=f"{spec.configuration.name}-{instance_num}",
        instance_num=instance_num,
        region="remote",
        host=hostname,
        ssh_user=ssh_user,
        ssh_keys=[ssh_key],
        ssh_proxy=ssh_proxy,
        ssh_proxy_keys=ssh_proxy_keys,
        env=env,
        internal_ip=internal_ip,
        instance_network=ssh_params.network,
        port=port or 22,
        blocks=blocks,
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
        select(FleetModel)
        .where(
            FleetModel.project_id == project.id,
            FleetModel.name.in_(names),
            FleetModel.deleted == False,
        )
        .options(joinedload(FleetModel.instances))
    )
    fleet_models = res.scalars().unique().all()
    fleets_ids = sorted([f.id for f in fleet_models])
    instances_ids = sorted([i.id for f in fleet_models for i in f.instances])
    await session.commit()
    logger.info("Deleting fleets: %s", [v.name for v in fleet_models])
    async with (
        get_locker(get_db().dialect_name).lock_ctx(FleetModel.__tablename__, fleets_ids),
        get_locker(get_db().dialect_name).lock_ctx(InstanceModel.__tablename__, instances_ids),
    ):
        # Refetch after lock
        # TODO: Lock instances with FOR UPDATE?
        # TODO: Do not lock fleet when deleting only instances
        res = await session.execute(
            select(FleetModel)
            .where(
                FleetModel.project_id == project.id,
                FleetModel.name.in_(names),
                FleetModel.deleted == False,
            )
            .options(
                selectinload(FleetModel.instances)
                .joinedload(InstanceModel.jobs)
                .load_only(JobModel.id)
            )
            .options(selectinload(FleetModel.runs))
            .execution_options(populate_existing=True)
            .order_by(FleetModel.id)  # take locks in order
            .with_for_update(key_share=True)
        )
        fleet_models = res.scalars().unique().all()
        fleets = [fleet_model_to_fleet(m) for m in fleet_models]
        for fleet in fleets:
            if fleet.spec.configuration.ssh_config is not None:
                _check_can_manage_ssh_fleets(user=user, project=project)
        for fleet_model in fleet_models:
            _terminate_fleet_instances(fleet_model=fleet_model, instance_nums=instance_nums)
            # TERMINATING fleets are deleted by process_fleets after instances are terminated
            if instance_nums is None:
                fleet_model.status = FleetStatus.TERMINATING
        await session.commit()


def fleet_model_to_fleet(
    fleet_model: FleetModel,
    include_deleted_instances: bool = False,
    include_sensitive: bool = False,
) -> Fleet:
    instance_models = fleet_model.instances
    if not include_deleted_instances:
        instance_models = [i for i in instance_models if not i.deleted]
    instances = [instances_services.instance_model_to_instance(i) for i in instance_models]
    instances = sorted(instances, key=lambda i: i.instance_num)
    spec = get_fleet_spec(fleet_model)
    if not include_sensitive:
        _remove_fleet_spec_sensitive_info(spec)
    return Fleet(
        id=fleet_model.id,
        name=fleet_model.name,
        project_name=fleet_model.project.name,
        spec=spec,
        created_at=fleet_model.created_at,
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
    instances_in_use = [i for i in fleet_model.instances if i.jobs and not i.deleted]
    selected_instance_in_use = instances_in_use
    if instance_nums is not None:
        selected_instance_in_use = [i for i in instances_in_use if i.instance_num in instance_nums]
    active_runs = [r for r in fleet_model.runs if not r.status.is_finished()]
    return len(selected_instance_in_use) > 0 or len(instances_in_use) == 0 and len(active_runs) > 0


def is_fleet_empty(fleet_model: FleetModel) -> bool:
    active_instances = [i for i in fleet_model.instances if not i.deleted]
    return len(active_instances) == 0


def get_fleet_requirements(fleet_spec: FleetSpec) -> Requirements:
    profile = fleet_spec.merged_profile
    requirements = Requirements(
        resources=fleet_spec.configuration.resources or ResourcesSpec(),
        max_price=profile.max_price,
        spot=get_policy_map(profile.spot_policy, default=SpotPolicy.ONDEMAND),
        reservation=fleet_spec.configuration.reservation,
    )
    return requirements


async def _create_fleet(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    spec: FleetSpec,
) -> Fleet:
    lock_namespace = f"fleet_names_{project.name}"
    if get_db().dialect_name == "sqlite":
        # Start new transaction to see committed changes after lock
        await session.commit()
    elif get_db().dialect_name == "postgresql":
        await session.execute(
            select(func.pg_advisory_xact_lock(string_to_lock_id(lock_namespace)))
        )

    lock, _ = get_locker(get_db().dialect_name).get_lockset(lock_namespace)
    async with lock:
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
                    spec=spec,
                    reservation=spec.configuration.reservation,
                    instance_num=i,
                )
                fleet_model.instances.append(instance_model)
        await session.commit()
        return fleet_model_to_fleet(fleet_model)


async def _update_fleet(
    session: AsyncSession,
    project: ProjectModel,
    spec: FleetSpec,
    current_resource: Optional[Fleet],
    force: bool,
    fleet_model: FleetModel,
) -> Fleet:
    fleet = fleet_model_to_fleet(fleet_model)
    _set_fleet_spec_defaults(fleet.spec)
    fleet_sensitive = fleet_model_to_fleet(fleet_model, include_sensitive=True)
    _set_fleet_spec_defaults(fleet_sensitive.spec)

    if not force:
        if current_resource is not None:
            _set_fleet_spec_defaults(current_resource.spec)
        if (
            current_resource is None
            or current_resource.id != fleet.id
            or current_resource.spec != fleet.spec
        ):
            raise ServerClientError(
                "Failed to apply plan. Resource has been changed. Try again or use force apply."
            )

    _check_can_update_fleet_spec(fleet_sensitive.spec, spec)

    spec_json = spec.json()
    fleet_model.spec = spec_json

    if (
        fleet_sensitive.spec.configuration.ssh_config is not None
        and spec.configuration.ssh_config is not None
    ):
        added_hosts, removed_hosts, changed_hosts = _calculate_ssh_hosts_changes(
            current=fleet_sensitive.spec.configuration.ssh_config.hosts,
            new=spec.configuration.ssh_config.hosts,
        )
        # `_check_can_update_fleet_spec` ensures hosts are not changed
        assert not changed_hosts, changed_hosts
        active_instance_nums: set[int] = set()
        removed_instance_nums: list[int] = []
        if removed_hosts or added_hosts:
            for instance_model in fleet_model.instances:
                if instance_model.deleted:
                    continue
                active_instance_nums.add(instance_model.instance_num)
                rci = get_instance_remote_connection_info(instance_model)
                if rci is None:
                    logger.error(
                        "Cloud instance %s in SSH fleet %s",
                        instance_model.id,
                        fleet_model.id,
                    )
                    continue
                if rci.host in removed_hosts:
                    removed_instance_nums.append(instance_model.instance_num)
        if added_hosts:
            await _check_ssh_hosts_not_yet_added(session, spec, fleet.id)
            for host in added_hosts.values():
                instance_num = _get_next_instance_num(active_instance_nums)
                instance_model = await create_fleet_ssh_instance_model(
                    project=project,
                    spec=spec,
                    ssh_params=spec.configuration.ssh_config,
                    env=spec.configuration.env,
                    instance_num=instance_num,
                    host=host,
                )
                fleet_model.instances.append(instance_model)
                active_instance_nums.add(instance_num)
        if removed_instance_nums:
            _terminate_fleet_instances(fleet_model, removed_instance_nums)

    await session.commit()
    return fleet_model_to_fleet(fleet_model)


def _can_update_fleet_spec(current_fleet_spec: FleetSpec, new_fleet_spec: FleetSpec) -> bool:
    try:
        _check_can_update_fleet_spec(current_fleet_spec, new_fleet_spec)
    except ServerClientError as e:
        logger.debug("Run cannot be updated: %s", repr(e))
        return False
    return True


M = TypeVar("M", bound=CoreModel)


def _check_can_update(*updatable_fields: str):
    def decorator(fn: Callable[[M, M, ModelDiff], None]) -> Callable[[M, M], None]:
        @wraps(fn)
        def inner(current: M, new: M):
            diff = _check_can_update_inner(current, new, updatable_fields)
            fn(current, new, diff)

        return inner

    return decorator


def _check_can_update_inner(current: M, new: M, updatable_fields: tuple[str, ...]) -> ModelDiff:
    diff = diff_models(current, new)
    changed_fields = diff.keys()
    if not (changed_fields <= set(updatable_fields)):
        raise ServerClientError(
            f"Failed to update fields {list(changed_fields)}."
            f" Can only update {list(updatable_fields)}."
        )
    return diff


@_check_can_update("configuration", "configuration_path")
def _check_can_update_fleet_spec(current: FleetSpec, new: FleetSpec, diff: ModelDiff):
    if "configuration" in diff:
        _check_can_update_fleet_configuration(current.configuration, new.configuration)


@_check_can_update("ssh_config")
def _check_can_update_fleet_configuration(
    current: FleetConfiguration, new: FleetConfiguration, diff: ModelDiff
):
    if "ssh_config" in diff:
        current_ssh_config = current.ssh_config
        new_ssh_config = new.ssh_config
        if current_ssh_config is None:
            if new_ssh_config is not None:
                raise ServerClientError("Fleet type changed from Cloud to SSH, cannot update")
        elif new_ssh_config is None:
            raise ServerClientError("Fleet type changed from SSH to Cloud, cannot update")
        else:
            _check_can_update_ssh_config(current_ssh_config, new_ssh_config)


@_check_can_update("hosts")
def _check_can_update_ssh_config(current: SSHParams, new: SSHParams, diff: ModelDiff):
    if "hosts" in diff:
        _, _, changed_hosts = _calculate_ssh_hosts_changes(current.hosts, new.hosts)
        if changed_hosts:
            raise ServerClientError(
                f"Hosts configuration changed, cannot update: {list(changed_hosts)}"
            )


def _calculate_ssh_hosts_changes(
    current: list[Union[SSHHostParams, str]], new: list[Union[SSHHostParams, str]]
) -> tuple[dict[str, Union[SSHHostParams, str]], set[str], set[str]]:
    current_hosts = {h if isinstance(h, str) else h.hostname: h for h in current}
    new_hosts = {h if isinstance(h, str) else h.hostname: h for h in new}
    added_hosts = {h: new_hosts[h] for h in new_hosts.keys() - current_hosts}
    removed_hosts = current_hosts.keys() - new_hosts
    changed_hosts: set[str] = set()
    for host in current_hosts.keys() & new_hosts:
        current_host = current_hosts[host]
        new_host = new_hosts[host]
        if isinstance(current_host, str) or isinstance(new_host, str):
            if current_host != new_host:
                changed_hosts.add(host)
        elif diff_models(
            current_host, new_host, reset={"identity_file": True, "proxy_jump": {"identity_file"}}
        ):
            changed_hosts.add(host)
    return added_hosts, removed_hosts, changed_hosts


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


async def _check_ssh_hosts_not_yet_added(
    session: AsyncSession, spec: FleetSpec, current_fleet_id: Optional[uuid.UUID] = None
):
    if spec.configuration.ssh_config and spec.configuration.ssh_config.hosts:
        # there are manually listed hosts, need to check them for existence
        active_instances = await list_active_remote_instances(session=session)

        existing_hosts = set()
        for instance in active_instances:
            # ignore instances belonging to the same fleet -- in-place update/recreate
            if current_fleet_id is not None and instance.fleet_id == current_fleet_id:
                continue
            instance_conn_info = RemoteConnectionInfo.parse_raw(
                cast(str, instance.remote_connection_info)
            )
            existing_hosts.add(instance_conn_info.host)

        instances_already_in_fleet = []
        for new_instance in spec.configuration.ssh_config.hosts:
            hostname = new_instance if isinstance(new_instance, str) else new_instance.hostname
            if hostname in existing_hosts:
                instances_already_in_fleet.append(hostname)

        if instances_already_in_fleet:
            raise ServerClientError(
                msg=f"Instances [{', '.join(instances_already_in_fleet)}] are already assigned to a fleet."
            )


def _remove_fleet_spec_sensitive_info(spec: FleetSpec):
    if spec.configuration.ssh_config is not None:
        spec.configuration.ssh_config.ssh_key = None
        for host in spec.configuration.ssh_config.hosts:
            if not isinstance(host, str):
                host.ssh_key = None


def _validate_fleet_spec_and_set_defaults(spec: FleetSpec):
    if spec.configuration.name is not None:
        validate_dstack_resource_name(spec.configuration.name)
    if spec.configuration.ssh_config is None and spec.configuration.nodes is None:
        raise ServerClientError("No ssh_config or nodes specified")
    if spec.configuration.ssh_config is not None and spec.configuration.nodes is not None:
        raise ServerClientError("ssh_config and nodes are mutually exclusive")
    if spec.configuration.ssh_config is not None:
        _validate_all_ssh_params_specified(spec.configuration.ssh_config)
        if spec.configuration.ssh_config.ssh_key is not None:
            _validate_ssh_key(spec.configuration.ssh_config.ssh_key)
        for host in spec.configuration.ssh_config.hosts:
            if isinstance(host, SSHHostParams) and host.ssh_key is not None:
                _validate_ssh_key(host.ssh_key)
        _validate_internal_ips(spec.configuration.ssh_config)
    _set_fleet_spec_defaults(spec)


def _set_fleet_spec_defaults(spec: FleetSpec):
    if spec.configuration.resources is not None:
        set_resources_defaults(spec.configuration.resources)


def _validate_all_ssh_params_specified(ssh_config: SSHParams):
    for host in ssh_config.hosts:
        if isinstance(host, str):
            if ssh_config.ssh_key is None:
                raise ServerClientError(f"No ssh key specified for host {host}")
            if ssh_config.user is None:
                raise ServerClientError(f"No ssh user specified for host {host}")
        else:
            if ssh_config.ssh_key is None and host.ssh_key is None:
                raise ServerClientError(f"No ssh key specified for host {host.hostname}")
            if ssh_config.user is None and host.user is None:
                raise ServerClientError(f"No ssh user specified for host {host.hostname}")


def _validate_ssh_key(ssh_key: SSHKey):
    if ssh_key.private is None:
        raise ServerClientError("Private key not provided")
    try:
        pkey_from_str(ssh_key.private)
    except ValueError:
        raise ServerClientError(
            "Unsupported key type. "
            "The key type should be RSA, ECDSA, or Ed25519 and should not be encrypted with passphrase."
        )


def _validate_internal_ips(ssh_config: SSHParams):
    internal_ips_num = 0
    for host in ssh_config.hosts:
        if not isinstance(host, str) and host.internal_ip is not None:
            internal_ips_num += 1
    if internal_ips_num != 0 and internal_ips_num != len(ssh_config.hosts):
        raise ServerClientError("internal_ip must be specified for all hosts")
    if internal_ips_num > 0 and ssh_config.network is not None:
        raise ServerClientError("internal_ip is mutually exclusive with network")


def _get_fleet_nodes_to_provision(spec: FleetSpec) -> int:
    if spec.configuration.nodes is None or spec.configuration.nodes.min is None:
        return 0
    return spec.configuration.nodes.min


def _terminate_fleet_instances(fleet_model: FleetModel, instance_nums: Optional[List[int]]):
    if is_fleet_in_use(fleet_model, instance_nums=instance_nums):
        if instance_nums is not None:
            raise ServerClientError(
                f"Failed to delete fleet {fleet_model.name} instances {instance_nums}. Fleet instances are in use."
            )
        raise ServerClientError(f"Failed to delete fleet {fleet_model.name}. Fleet is in use.")
    for instance in fleet_model.instances:
        if instance_nums is not None and instance.instance_num not in instance_nums:
            continue
        if instance.status == InstanceStatus.TERMINATED:
            instance.deleted = True
        else:
            instance.status = InstanceStatus.TERMINATING


def _get_next_instance_num(instance_nums: set[int]) -> int:
    if not instance_nums:
        return 0
    min_instance_num = min(instance_nums)
    if min_instance_num > 0:
        return 0
    instance_num = min_instance_num + 1
    while True:
        if instance_num not in instance_nums:
            return instance_num
        instance_num += 1
