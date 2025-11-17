import math
from typing import List, Optional

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
from dstack._internal.server.db import AsyncSession
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


DEFAULT_MAX_OFFERS = 50


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
    pool_offers = await _get_pool_offers(
        session=session,
        project=project,
        run_spec=run_spec,
        job=jobs[0],
        volumes=volumes,
    )

    # Get offers once for all jobs
    offers = []
    if profile.creation_policy == CreationPolicy.REUSE_OR_CREATE:
        offers = await get_offers_by_requirements(
            project=project,
            profile=profile,
            requirements=jobs[0].job_spec.requirements,
            exclude_not_available=False,
            multinode=jobs[0].job_spec.jobs_per_replica > 1,
            volumes=volumes,
            privileged=jobs[0].job_spec.privileged,
            instance_mounts=check_run_spec_requires_instance_mounts(run_spec),
        )

    job_plans = []
    for job in jobs:
        job_offers: List[InstanceOfferWithAvailability] = []
        job_offers.extend(pool_offers)
        job_offers.extend(offer for _, offer in offers)
        job_offers.sort(key=lambda offer: not offer.availability.is_available())

        job_spec = job.job_spec
        remove_job_spec_sensitive_info(job_spec)

        job_plan = JobPlan(
            job_spec=job_spec,
            offers=job_offers[: (max_offers or DEFAULT_MAX_OFFERS)],
            total_offers=len(job_offers),
            max_price=max((offer.price for offer in job_offers), default=None),
        )
        job_plans.append(job_plan)

    run_spec.run_name = run_name
    return job_plans


async def find_optimal_fleet_with_offers(
    project: ProjectModel,
    fleet_models: list[FleetModel],
    run_model: Optional[RunModel],
    run_spec: RunSpec,
    job: Job,
    master_job_provisioning_data: Optional[JobProvisioningData],
    volumes: Optional[list[list[Volume]]],
) -> tuple[
    Optional[FleetModel],
    list[tuple[InstanceModel, InstanceOfferWithAvailability]],
    list[tuple[Backend, InstanceOfferWithAvailability]],
]:
    """
    Finds the optimal fleet for the run among the given fleet models and returns
    the fleet model, pool offers with instances, and backend offers.
    Returns empty backend offers if run_model.fleet is set since
    backend offer from this function are needed only for run plan.
    """
    if run_model is not None and run_model.fleet is not None:
        # Using the fleet that was already chosen by the master job
        fleet_instance_offers = _get_run_fleet_instance_offers(
            fleet_model=run_model.fleet,
            run_spec=run_spec,
            job=job,
            master_job_provisioning_data=master_job_provisioning_data,
            volumes=volumes,
        )
        return run_model.fleet, fleet_instance_offers, []

    nodes_required_num = get_nodes_required_num(run_spec)
    # The current strategy is first to consider fleets that can accommodate
    # the run without additional provisioning and choose the one with the cheapest pool offer.
    # Then choose a fleet with the cheapest pool offer among all fleets with pool offers.
    # If there are no fleets with pool offers, choose a fleet with a cheapest backend offer.
    # Fallback to autocreated fleet if fleets have no pool or backend offers.
    # TODO: Consider trying all backend offers and then choosing a fleet.
    candidate_fleets_with_offers: list[
        tuple[
            Optional[FleetModel],
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

        fleet_instance_offers = _get_run_fleet_instance_offers(
            fleet_model=candidate_fleet_model,
            run_spec=run_spec,
            job=job,
            # No need to pass master_job_provisioning_data for master job
            # as all pool offers are suitable.
            master_job_provisioning_data=None,
            volumes=volumes,
        )
        fleet_has_pool_capacity = nodes_required_num <= len(fleet_instance_offers)
        fleet_cheapest_instance_offer = math.inf
        if len(fleet_instance_offers) > 0:
            fleet_cheapest_instance_offer = fleet_instance_offers[0][1].price

        try:
            check_can_create_new_cloud_instance_in_fleet(candidate_fleet)
            profile, requirements = get_run_profile_and_requirements_in_fleet(
                job=job,
                run_spec=run_spec,
                fleet=candidate_fleet,
            )
        except ValueError:
            fleet_backend_offers = []
        else:
            # Master job offers must be in the same cluster as existing instances.
            master_instance_provisioning_data = get_fleet_master_instance_provisioning_data(
                fleet_model=candidate_fleet_model,
                fleet_spec=candidate_fleet.spec,
            )
            # Handle multinode for old jobs that don't have requirements.multinode set.
            # TODO: Drop multinode param.
            multinode = requirements.multinode or is_multinode_job(job)
            fleet_backend_offers = await get_offers_by_requirements(
                project=project,
                profile=profile,
                requirements=requirements,
                exclude_not_available=True,
                multinode=multinode,
                master_job_provisioning_data=master_instance_provisioning_data,
                volumes=volumes,
                privileged=job.job_spec.privileged,
                instance_mounts=check_run_spec_requires_instance_mounts(run_spec),
            )

        fleet_cheapest_backend_offer = math.inf
        if len(fleet_backend_offers) > 0:
            fleet_cheapest_backend_offer = fleet_backend_offers[0][1].price

        if not _run_can_fit_into_fleet(run_spec, candidate_fleet):
            logger.debug("Skipping fleet %s from consideration: run cannot fit into fleet")
            continue

        fleet_priority = (
            not fleet_has_pool_capacity,
            fleet_cheapest_instance_offer,
            fleet_cheapest_backend_offer,
        )
        candidate_fleets_with_offers.append(
            (
                candidate_fleet_model,
                fleet_instance_offers,
                fleet_backend_offers,
                len(fleet_instance_offers),
                len(fleet_backend_offers),
                fleet_priority,
            )
        )
    if len(candidate_fleets_with_offers) == 0:
        return None, [], []
    if (
        not FeatureFlags.AUTOCREATED_FLEETS_DISABLED
        and run_spec.merged_profile.fleets is None
        and all(t[3] == 0 and t[4] == 0 for t in candidate_fleets_with_offers)
    ):
        # If fleets are not specified and no fleets have available pool
        # or backend offers, create a new fleet.
        # This is for compatibility with non-fleet-first UX when runs created new fleets
        # if there are no instances to reuse.
        return None, [], []
    candidate_fleets_with_offers.sort(key=lambda t: t[-1])
    return candidate_fleets_with_offers[0][:3]


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


def _get_run_fleet_instance_offers(
    fleet_model: FleetModel,
    run_spec: RunSpec,
    job: Job,
    master_job_provisioning_data: Optional[JobProvisioningData] = None,
    volumes: Optional[List[List[Volume]]] = None,
) -> list[tuple[InstanceModel, InstanceOfferWithAvailability]]:
    pool_instances = fleet_model.instances
    instances_with_offers: list[tuple[InstanceModel, InstanceOfferWithAvailability]]
    profile = run_spec.merged_profile
    multinode = is_multinode_job(job)
    nonshared_instances = filter_pool_instances(
        pool_instances=pool_instances,
        profile=profile,
        requirements=job.job_spec.requirements,
        status=InstanceStatus.IDLE,
        fleet_model=fleet_model,
        multinode=multinode,
        master_job_provisioning_data=master_job_provisioning_data,
        volumes=volumes,
        shared=False,
    )
    instances_with_offers = [
        (instance, common_utils.get_or_error(get_instance_offer(instance)))
        for instance in nonshared_instances
    ]
    shared_instances_with_offers = get_shared_pool_instances_with_offers(
        pool_instances=pool_instances,
        profile=profile,
        requirements=job.job_spec.requirements,
        idle_only=True,
        fleet_model=fleet_model,
        multinode=multinode,
        volumes=volumes,
    )
    instances_with_offers.extend(shared_instances_with_offers)
    instances_with_offers.sort(key=lambda instance_with_offer: instance_with_offer[0].price or 0)
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


async def _get_pool_offers(
    session: AsyncSession,
    project: ProjectModel,
    run_spec: RunSpec,
    job: Job,
    volumes: List[List[Volume]],
) -> list[InstanceOfferWithAvailability]:
    pool_offers: list[InstanceOfferWithAvailability] = []

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
    for _, offer in shared_instances_with_offers:
        pool_offers.append(offer)

    nonshared_instances = filter_pool_instances(
        pool_instances=pool_instances,
        profile=run_spec.merged_profile,
        requirements=job.job_spec.requirements,
        multinode=multinode,
        volumes=volumes,
        shared=False,
    )
    for instance in nonshared_instances:
        offer = get_instance_offer(instance)
        if offer is None:
            continue
        offer.availability = InstanceAvailability.BUSY
        if instance.status == InstanceStatus.IDLE:
            offer.availability = InstanceAvailability.IDLE
        pool_offers.append(offer)

    pool_offers.sort(key=lambda offer: offer.price)
    return pool_offers
