import math
from typing import Optional, Union

from sqlalchemy import and_, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager, noload

from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.models.fleets import Fleet, InstanceGroupPlacement
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceStatus,
)
from dstack._internal.core.models.profiles import CreationPolicy, Profile
from dstack._internal.core.models.runs import (
    Job,
    JobPlan,
    JobProvisioningData,
    Requirements,
    RunSpec,
)
from dstack._internal.core.models.volumes import Volume
from dstack._internal.server.models import FleetModel, InstanceModel, ProjectModel, RunModel
from dstack._internal.server.services.fleets import (
    check_can_create_new_cloud_instance_in_fleet,
    fleet_model_to_fleet,
    get_fleet_master_instance_provisioning_data,
    get_fleet_requirements,
)
from dstack._internal.server.services.instances import (
    filter_pool_instances,
    get_instance_offer,
    get_pool_instances,
    get_shared_pool_instances_with_offers,
)
from dstack._internal.server.services.jobs import (
    get_instances_ids_with_detaching_volumes,
    get_job_configured_volumes,
    get_jobs_from_run_spec,
    is_multinode_job,
    remove_job_spec_sensitive_info,
)
from dstack._internal.server.services.offers import get_offers_by_requirements
from dstack._internal.server.services.requirements.combine import (
    combine_fleet_and_run_profiles,
    combine_fleet_and_run_requirements,
)
from dstack._internal.server.services.runs.spec import (
    check_run_spec_requires_instance_mounts,
    get_nodes_required_num,
)
from dstack._internal.server.services.secrets import get_project_secrets_mapping
from dstack._internal.settings import FeatureFlags
from dstack._internal.utils import common as common_utils
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


_DEFAULT_MAX_OFFERS = 50
# To avoid too many offers from being processed per fleet when searching for optimal fleet.
# Without the limit, time and peak memory usage spike since
# they grow linearly with the number of fleets.
_PER_FLEET_MAX_OFFERS = 100


async def get_job_plans(
    session: AsyncSession,
    project: ProjectModel,
    profile: Profile,
    run_spec: RunSpec,
    max_offers: Optional[int],
) -> list[JobPlan]:
    run_name = run_spec.run_name
    if run_spec.run_name is None:
        # Set/unset dummy run name to generate job names for run plan.
        run_spec.run_name = "dry-run"

    secrets = await get_project_secrets_mapping(session=session, project=project)
    jobs = await get_jobs_from_run_spec(
        run_spec=run_spec,
        secrets=secrets,
        replica_num=0,
    )
    volumes = await get_job_configured_volumes(
        session=session,
        project=project,
        run_spec=run_spec,
        job_num=0,
    )
    candidate_fleet_models = await _select_candidate_fleet_models(
        session=session,
        project=project,
        run_model=None,
        run_spec=run_spec,
    )
    fleet_model, instance_offers, backend_offers = await find_optimal_fleet_with_offers(
        project=project,
        fleet_models=candidate_fleet_models,
        run_model=None,
        run_spec=run_spec,
        job=jobs[0],
        master_job_provisioning_data=None,
        volumes=volumes,
        exclude_not_available=False,
    )
    if _should_force_non_fleet_offers(run_spec) or (
        FeatureFlags.AUTOCREATED_FLEETS_ENABLED and profile.fleets is None and fleet_model is None
    ):
        # Keep the old behavior returning all offers irrespective of fleets.
        # Needed for supporting offers with autocreated fleets flow (and for `dstack offer`).
        instance_offers, backend_offers = await _get_non_fleet_offers(
            session=session,
            project=project,
            profile=profile,
            run_spec=run_spec,
            job=jobs[0],
            volumes=volumes,
        )

    job_plans = []
    for job in jobs:
        job_plan = _get_job_plan(
            instance_offers=instance_offers,
            backend_offers=backend_offers,
            profile=profile,
            job=job,
            max_offers=max_offers,
        )
        job_plans.append(job_plan)

    run_spec.run_name = run_name
    return job_plans


async def get_run_candidate_fleet_models_filters(
    session: AsyncSession,
    project: ProjectModel,
    run_model: Optional[RunModel],
    run_spec: RunSpec,
) -> tuple[list, list]:
    """
    Returns ORM fleet and instance filters for selecting run candidate fleet models with instances.
    """
    # If another job freed the instance but is still trying to detach volumes,
    # do not provision on it to prevent attaching volumes that are currently detaching.
    detaching_instances_ids = await get_instances_ids_with_detaching_volumes(session)
    fleet_filters = [
        FleetModel.project_id == project.id,
        FleetModel.deleted == False,
    ]
    if run_model is not None and run_model.fleet is not None:
        fleet_filters.append(FleetModel.id == run_model.fleet_id)
    if run_spec.merged_profile.fleets is not None:
        fleet_filters.append(FleetModel.name.in_(run_spec.merged_profile.fleets))
    instance_filters = [
        InstanceModel.deleted == False,
        InstanceModel.id.not_in(detaching_instances_ids),
    ]
    return fleet_filters, instance_filters


async def select_run_candidate_fleet_models_with_filters(
    session: AsyncSession,
    fleet_filters: list,
    instance_filters: list,
    lock_instances: bool,
) -> tuple[list[FleetModel], list[FleetModel]]:
    # Selecting fleets in two queries since Postgres does not allow
    # locking nullable side of an outer join. So, first lock instances with inner join.
    # Then select left out fleets without instances.
    stmt = (
        select(FleetModel)
        .join(FleetModel.instances)
        .where(*fleet_filters)
        .where(*instance_filters)
        .options(contains_eager(FleetModel.instances))
        .execution_options(populate_existing=True)
    )
    if lock_instances:
        stmt = stmt.order_by(InstanceModel.id).with_for_update(  # take locks in order
            key_share=True, of=InstanceModel
        )
    res = await session.execute(stmt)
    fleet_models_with_instances = list(res.unique().scalars().all())
    fleet_models_with_instances_ids = [f.id for f in fleet_models_with_instances]
    res = await session.execute(
        select(FleetModel)
        .outerjoin(FleetModel.instances)
        .where(
            *fleet_filters,
            FleetModel.id.not_in(fleet_models_with_instances_ids),
        )
        .where(
            or_(
                InstanceModel.id.is_(None),
                not_(and_(*instance_filters)),
            )
        )
        .options(noload(FleetModel.instances))
        .execution_options(populate_existing=True)
    )
    fleet_models_without_instances = list(res.unique().scalars().all())
    return fleet_models_with_instances, fleet_models_without_instances


async def find_optimal_fleet_with_offers(
    project: ProjectModel,
    fleet_models: list[FleetModel],
    run_model: Optional[RunModel],
    run_spec: RunSpec,
    job: Job,
    master_job_provisioning_data: Optional[JobProvisioningData],
    volumes: Optional[list[list[Volume]]],
    exclude_not_available: bool,
) -> tuple[
    Optional[FleetModel],
    list[tuple[InstanceModel, InstanceOfferWithAvailability]],
    list[tuple[Backend, InstanceOfferWithAvailability]],
]:
    """
    Finds the optimal fleet for the run among the given fleets and returns
    the fleet model, pool offers with instances, and backend offers.
    Returns empty backend offers if run_model.fleet is set since
    backend offer from this function are needed only for run plan.
    Only available offers are considered for selecting fleets but may return
    either available or all offers depending on `exclude_not_available`.
    """
    if run_model is not None and run_model.fleet is not None:
        # Using the fleet that was already chosen by the master job
        instance_offers = _get_instance_offers_in_fleet(
            fleet_model=run_model.fleet,
            run_spec=run_spec,
            job=job,
            master_job_provisioning_data=master_job_provisioning_data,
            volumes=volumes,
        )
        if exclude_not_available:
            instance_offers = _exclude_non_available_instance_offers(instance_offers)
        return run_model.fleet, instance_offers, []

    nodes_required_num = get_nodes_required_num(run_spec)
    # The current strategy is first to consider fleets that can accommodate
    # the run without additional provisioning and choose the one with the cheapest pool offer.
    # Then choose a fleet with the cheapest pool offer among all fleets with pool offers.
    # If there are no fleets with pool offers, choose a fleet with a cheapest backend offer.
    # TODO: Consider trying all backend offers and then choosing a fleet.
    candidate_fleets_with_offers: list[
        tuple[
            FleetModel,
            list[tuple[InstanceModel, InstanceOfferWithAvailability]],
            list[tuple[Backend, InstanceOfferWithAvailability]],
            int,
            int,
            tuple[int, float, float],
        ]
    ] = []
    for candidate_fleet_model in fleet_models:
        candidate_fleet = fleet_model_to_fleet(candidate_fleet_model)
        if (
            is_multinode_job(job)
            and candidate_fleet.spec.configuration.placement != InstanceGroupPlacement.CLUSTER
        ):
            # Limit multinode runs to cluster fleets to guarantee best connectivity.
            continue

        if not _run_can_fit_into_fleet(run_spec, candidate_fleet):
            logger.debug("Skipping fleet %s from consideration: run cannot fit into fleet")
            continue

        instance_offers = _get_instance_offers_in_fleet(
            fleet_model=candidate_fleet_model,
            run_spec=run_spec,
            job=job,
            # No need to pass master_job_provisioning_data for master job
            # as all pool offers are suitable.
            master_job_provisioning_data=None,
            volumes=volumes,
        )
        available_instance_offers = _exclude_non_available_instance_offers(instance_offers)
        if exclude_not_available:
            instance_offers = available_instance_offers
        has_pool_capacity = nodes_required_num <= len(available_instance_offers)
        min_instance_offer_price = _get_min_instance_or_backend_offer_price(
            available_instance_offers
        )

        backend_offers = await _get_backend_offers_in_fleet(
            project=project,
            fleet_model=candidate_fleet_model,
            fleet=candidate_fleet,
            run_spec=run_spec,
            job=job,
            volumes=volumes,
            max_offers=_PER_FLEET_MAX_OFFERS,
        )

        available_backend_offers = _exclude_non_available_backend_offers(backend_offers)
        min_backend_offer_price = _get_min_instance_or_backend_offer_price(
            available_backend_offers
        )

        fleet_priority = (
            not has_pool_capacity,
            min_instance_offer_price,
            min_backend_offer_price,
        )
        candidate_fleets_with_offers.append(
            (
                candidate_fleet_model,
                instance_offers,
                backend_offers,
                len(available_instance_offers),
                len(available_backend_offers),
                fleet_priority,
            )
        )

    if len(candidate_fleets_with_offers) == 0:
        return None, [], []

    if (
        FeatureFlags.AUTOCREATED_FLEETS_ENABLED
        and run_spec.merged_profile.fleets is None
        and all(t[3] == 0 and t[4] == 0 for t in candidate_fleets_with_offers)
    ):
        # If fleets are not specified and no fleets have available pool
        # or backend offers, create a new fleet.
        # This is for compatibility with non-fleet-first UX when runs created new fleets
        # if there are no instances to reuse.
        return None, [], []

    candidate_fleets_with_offers.sort(key=lambda t: t[-1])
    optimal_fleet_model, instance_offers = candidate_fleets_with_offers[0][:2]
    # Refetch backend offers without limit to return all offers for the optimal fleet.
    backend_offers = await _get_backend_offers_in_fleet(
        project=project,
        fleet_model=optimal_fleet_model,
        run_spec=run_spec,
        job=job,
        volumes=volumes,
        max_offers=None,
    )
    if exclude_not_available:
        backend_offers = _exclude_non_available_backend_offers(backend_offers)
    return optimal_fleet_model, instance_offers, backend_offers


def get_run_profile_and_requirements_in_fleet(
    job: Job,
    run_spec: RunSpec,
    fleet: Fleet,
) -> tuple[Profile, Requirements]:
    profile = combine_fleet_and_run_profiles(fleet.spec.merged_profile, run_spec.merged_profile)
    if profile is None:
        raise ValueError("Cannot combine fleet profile")
    fleet_requirements = get_fleet_requirements(fleet.spec)
    requirements = combine_fleet_and_run_requirements(
        fleet_requirements, job.job_spec.requirements
    )
    if requirements is None:
        raise ValueError("Cannot combine fleet requirements")
    return profile, requirements


async def _select_candidate_fleet_models(
    session: AsyncSession,
    project: ProjectModel,
    run_model: Optional[RunModel],
    run_spec: RunSpec,
) -> list[FleetModel]:
    fleet_filters, instance_filters = await get_run_candidate_fleet_models_filters(
        session=session,
        project=project,
        run_model=run_model,
        run_spec=run_spec,
    )
    (
        fleet_models_with_instances,
        fleet_models_without_instances,
    ) = await select_run_candidate_fleet_models_with_filters(
        session=session,
        fleet_filters=fleet_filters,
        instance_filters=instance_filters,
        lock_instances=False,
    )
    return fleet_models_with_instances + fleet_models_without_instances


def _get_instance_offers_in_fleet(
    fleet_model: FleetModel,
    run_spec: RunSpec,
    job: Job,
    master_job_provisioning_data: Optional[JobProvisioningData] = None,
    volumes: Optional[list[list[Volume]]] = None,
) -> list[tuple[InstanceModel, InstanceOfferWithAvailability]]:
    pool_instances = fleet_model.instances
    profile = run_spec.merged_profile
    multinode = is_multinode_job(job)
    nonshared_instances = filter_pool_instances(
        pool_instances=pool_instances,
        profile=profile,
        requirements=job.job_spec.requirements,
        fleet_model=fleet_model,
        multinode=multinode,
        master_job_provisioning_data=master_job_provisioning_data,
        volumes=volumes,
        shared=False,
    )
    instances_with_offers = _get_offers_from_instances(nonshared_instances)
    shared_instances_with_offers = get_shared_pool_instances_with_offers(
        pool_instances=pool_instances,
        profile=profile,
        requirements=job.job_spec.requirements,
        fleet_model=fleet_model,
        multinode=multinode,
        volumes=volumes,
    )
    instances_with_offers.extend(shared_instances_with_offers)
    instances_with_offers.sort(key=lambda o: o[0].price or 0)
    return instances_with_offers


def _run_can_fit_into_fleet(run_spec: RunSpec, fleet: Fleet) -> bool:
    """
    Returns `False` if the run cannot fit into fleet for sure.
    This is helpful heuristic to avoid even considering fleets too small for a run.
    A run may not fit even if this function returns `True`.
    This will lead to some jobs failing due to exceeding `nodes.max`
    or more than `nodes.max` instances being provisioned
    and eventually removed by the fleet consolidation logic.
    """
    # No check for cloud fleets with blocks > 1 since we don't know
    # how many jobs such fleets can accommodate.
    nodes_required_num = get_nodes_required_num(run_spec)
    if (
        fleet.spec.configuration.nodes is not None
        and fleet.spec.configuration.blocks == 1
        and fleet.spec.configuration.nodes.max is not None
    ):
        busy_instances = [i for i in fleet.instances if i.busy_blocks > 0]
        fleet_available_capacity = fleet.spec.configuration.nodes.max - len(busy_instances)
        if fleet_available_capacity < nodes_required_num:
            return False
    elif fleet.spec.configuration.ssh_config is not None:
        # Currently assume that each idle block can run a job.
        # TODO: Take resources / eligible offers into account.
        total_idle_blocks = 0
        for instance in fleet.instances:
            total_blocks = instance.total_blocks or 1
            total_idle_blocks += total_blocks - instance.busy_blocks
        if total_idle_blocks < nodes_required_num:
            return False
    return True


async def _get_backend_offers_in_fleet(
    project: ProjectModel,
    fleet_model: FleetModel,
    run_spec: RunSpec,
    job: Job,
    volumes: Optional[list[list[Volume]]],
    fleet: Optional[Fleet] = None,
    max_offers: Optional[int] = None,
) -> list[tuple[Backend, InstanceOfferWithAvailability]]:
    if fleet is None:
        fleet = fleet_model_to_fleet(fleet_model)
    try:
        check_can_create_new_cloud_instance_in_fleet(fleet)
        profile, requirements = get_run_profile_and_requirements_in_fleet(
            job=job,
            run_spec=run_spec,
            fleet=fleet,
        )
    except ValueError:
        backend_offers = []
    else:
        # Master job offers must be in the same cluster as existing instances.
        master_instance_provisioning_data = get_fleet_master_instance_provisioning_data(
            fleet_model=fleet_model,
            fleet_spec=fleet.spec,
        )
        # Handle multinode for old jobs that don't have requirements.multinode set.
        # TODO: Drop multinode param.
        multinode = requirements.multinode or is_multinode_job(job)
        backend_offers = await get_offers_by_requirements(
            project=project,
            profile=profile,
            requirements=requirements,
            multinode=multinode,
            master_job_provisioning_data=master_instance_provisioning_data,
            volumes=volumes,
            privileged=job.job_spec.privileged,
            instance_mounts=check_run_spec_requires_instance_mounts(run_spec),
            max_offers=max_offers,
        )
    return backend_offers


async def _get_pool_offers(
    session: AsyncSession,
    project: ProjectModel,
    run_spec: RunSpec,
    job: Job,
    volumes: list[list[Volume]],
) -> list[tuple[InstanceModel, InstanceOfferWithAvailability]]:
    pool_offers: list[tuple[InstanceModel, InstanceOfferWithAvailability]] = []
    detaching_instances_ids = await get_instances_ids_with_detaching_volumes(session)
    pool_instances = await get_pool_instances(session, project)
    pool_instances = [i for i in pool_instances if i.id not in detaching_instances_ids]
    multinode = is_multinode_job(job)
    shared_instances_with_offers = get_shared_pool_instances_with_offers(
        pool_instances=pool_instances,
        profile=run_spec.merged_profile,
        requirements=job.job_spec.requirements,
        volumes=volumes,
        multinode=multinode,
    )
    for offer in shared_instances_with_offers:
        pool_offers.append(offer)

    nonshared_instances = filter_pool_instances(
        pool_instances=pool_instances,
        profile=run_spec.merged_profile,
        requirements=job.job_spec.requirements,
        multinode=multinode,
        volumes=volumes,
        shared=False,
    )
    nonshared_instances_with_offers = _get_offers_from_instances(nonshared_instances)
    pool_offers.extend(nonshared_instances_with_offers)
    pool_offers.sort(key=lambda o: o[1].price)
    return pool_offers


async def _get_non_fleet_offers(
    session: AsyncSession,
    project: ProjectModel,
    profile: Profile,
    run_spec: RunSpec,
    job: Job,
    volumes: list[list[Volume]],
) -> tuple[
    list[tuple[InstanceModel, InstanceOfferWithAvailability]],
    list[tuple[Backend, InstanceOfferWithAvailability]],
]:
    """
    Returns instance and backend offers for job irrespective of fleets,
    i.e. all pool instances and project backends matching the spec.
    """
    instance_offers = await _get_pool_offers(
        session=session,
        project=project,
        run_spec=run_spec,
        job=job,
        volumes=volumes,
    )
    backend_offers = await get_offers_by_requirements(
        project=project,
        profile=profile,
        requirements=job.job_spec.requirements,
        exclude_not_available=False,
        multinode=is_multinode_job(job),
        volumes=volumes,
        privileged=job.job_spec.privileged,
        instance_mounts=check_run_spec_requires_instance_mounts(run_spec),
    )
    return instance_offers, backend_offers


def _get_job_plan(
    instance_offers: list[tuple[InstanceModel, InstanceOfferWithAvailability]],
    backend_offers: list[tuple[Backend, InstanceOfferWithAvailability]],
    profile: Profile,
    job: Job,
    max_offers: Optional[int],
) -> JobPlan:
    job_offers: list[InstanceOfferWithAvailability] = []
    job_offers.extend(offer for _, offer in instance_offers)
    if profile.creation_policy == CreationPolicy.REUSE_OR_CREATE:
        job_offers.extend(offer for _, offer in backend_offers)
    job_offers.sort(key=lambda offer: not offer.availability.is_available())
    remove_job_spec_sensitive_info(job.job_spec)
    return JobPlan(
        job_spec=job.job_spec,
        offers=job_offers[: (max_offers or _DEFAULT_MAX_OFFERS)],
        total_offers=len(job_offers),
        max_price=max((offer.price for offer in job_offers), default=None),
    )


def _should_force_non_fleet_offers(run_spec: RunSpec) -> bool:
    # A hack to force non-fleet offers for `dstack offer` command that uses
    # get run plan API to show offers and the only way to distinguish it is commands.
    # Assuming real runs will not use such commands.
    return run_spec.configuration.type == "task" and run_spec.configuration.commands == [":"]


def _get_offers_from_instances(
    instances: list[InstanceModel],
) -> list[tuple[InstanceModel, InstanceOfferWithAvailability]]:
    instances_with_offers = []
    for instance in instances:
        offer = common_utils.get_or_error(get_instance_offer(instance))
        offer.availability = InstanceAvailability.BUSY
        if instance.status == InstanceStatus.IDLE:
            offer.availability = InstanceAvailability.IDLE
        instances_with_offers.append((instance, offer))
    return instances_with_offers


def _get_min_instance_or_backend_offer_price(
    offers: Union[
        list[tuple[InstanceModel, InstanceOfferWithAvailability]],
        list[tuple[Backend, InstanceOfferWithAvailability]],
    ],
) -> float:
    min_offer_price = math.inf
    if len(offers) > 0:
        min_offer_price = offers[0][1].price
    return min_offer_price


def _exclude_non_available_instance_offers(
    instance_offers: list[tuple[InstanceModel, InstanceOfferWithAvailability]],
) -> list[tuple[InstanceModel, InstanceOfferWithAvailability]]:
    return [
        (instance, offer)
        for instance, offer in instance_offers
        if offer.availability.is_available()
    ]


def _exclude_non_available_backend_offers(
    backend_offers: list[tuple[Backend, InstanceOfferWithAvailability]],
) -> list[tuple[Backend, InstanceOfferWithAvailability]]:
    return [
        (backend, offer) for backend, offer in backend_offers if offer.availability.is_available()
    ]
