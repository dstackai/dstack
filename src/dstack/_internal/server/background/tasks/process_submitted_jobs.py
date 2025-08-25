import asyncio
import itertools
import math
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import and_, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager, joinedload, load_only, noload, selectinload

from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.base.compute import ComputeWithVolumeSupport
from dstack._internal.core.errors import BackendError, ServerClientError
from dstack._internal.core.models.common import NetworkMode
from dstack._internal.core.models.fleets import (
    Fleet,
    FleetConfiguration,
    FleetSpec,
    FleetStatus,
    InstanceGroupPlacement,
)
from dstack._internal.core.models.instances import InstanceOfferWithAvailability, InstanceStatus
from dstack._internal.core.models.profiles import (
    DEFAULT_RUN_TERMINATION_IDLE_TIME,
    CreationPolicy,
    TerminationPolicy,
)
from dstack._internal.core.models.resources import Memory, Range
from dstack._internal.core.models.runs import (
    Job,
    JobProvisioningData,
    JobRuntimeData,
    JobStatus,
    JobTerminationReason,
    Run,
    RunSpec,
)
from dstack._internal.core.models.volumes import Volume
from dstack._internal.core.services.profiles import get_termination
from dstack._internal.server import settings
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import (
    FleetModel,
    InstanceModel,
    JobModel,
    ProjectModel,
    RunModel,
    UserModel,
    VolumeAttachmentModel,
    VolumeModel,
)
from dstack._internal.server.services.backends import get_project_backend_by_type_or_error
from dstack._internal.server.services.fleets import (
    fleet_model_to_fleet,
    get_fleet_requirements,
)
from dstack._internal.server.services.instances import (
    filter_pool_instances,
    get_instance_offer,
    get_instance_provisioning_data,
    get_shared_pool_instances_with_offers,
)
from dstack._internal.server.services.jobs import (
    check_can_attach_job_volumes,
    find_job,
    get_instances_ids_with_detaching_volumes,
    get_job_configured_volume_models,
    get_job_configured_volumes,
    get_job_runtime_data,
)
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.offers import get_offers_by_requirements
from dstack._internal.server.services.requirements.combine import (
    combine_fleet_and_run_profiles,
    combine_fleet_and_run_requirements,
)
from dstack._internal.server.services.runs import (
    check_run_spec_requires_instance_mounts,
    run_model_to_run,
)
from dstack._internal.server.services.volumes import (
    volume_model_to_volume,
)
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils import common as common_utils
from dstack._internal.utils import env as env_utils
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


# Track when we last processed a job.
# This is needed for a trick:
# If no tasks were processed recently, we force batch_size 1.
# If there are lots of runs/jobs with same offers submitted,
# we warm up the cache instead of requesting the offers concurrently.
# Mostly useful when runs are submitted via API without getting run plan first.
BATCH_SIZE_RESET_TIMEOUT = timedelta(minutes=2)
last_processed_at: Optional[datetime] = None


async def process_submitted_jobs(batch_size: int = 1):
    tasks = []
    effective_batch_size = _get_effective_batch_size(batch_size)
    for _ in range(effective_batch_size):
        tasks.append(_process_next_submitted_job())
    await asyncio.gather(*tasks)


def _get_effective_batch_size(batch_size: int) -> int:
    if (
        last_processed_at is None
        or last_processed_at < common_utils.get_current_datetime() - BATCH_SIZE_RESET_TIMEOUT
    ):
        return 1
    return batch_size


@sentry_utils.instrument_background_task
async def _process_next_submitted_job():
    lock, lockset = get_locker(get_db().dialect_name).get_lockset(JobModel.__tablename__)
    async with get_session_ctx() as session:
        async with lock:
            res = await session.execute(
                select(JobModel)
                .join(JobModel.run)
                .where(
                    JobModel.status == JobStatus.SUBMITTED,
                    JobModel.id.not_in(lockset),
                )
                .options(load_only(JobModel.id))
                # Jobs are process in FIFO sorted by priority globally,
                # thus runs from different projects can "overtake" each other by using higher priorities.
                # That's not a big problem as long as projects do not compete for the same compute resources.
                # Jobs with lower priorities from other projects will be processed without major lag
                # as long as new higher priority runs are not constantly submitted.
                # TODO: Consider processing jobs from different projects fairly/round-robin
                # Fully fair processing can be tricky to implement via the current DB queue as
                # there can be many projects and we are limited by the max DB connections.
                .order_by(RunModel.priority.desc(), JobModel.last_processed_at.asc())
                .limit(1)
                .with_for_update(
                    skip_locked=True,
                    key_share=True,
                    # Do not lock joined run, only job.
                    # Locking run here may cause deadlock.
                    of=JobModel,
                )
            )
            job_model = res.scalar()
            if job_model is None:
                return
            lockset.add(job_model.id)
        job_model_id = job_model.id
        try:
            await _process_submitted_job(session=session, job_model=job_model)
        finally:
            lockset.difference_update([job_model_id])
        global last_processed_at
        last_processed_at = common_utils.get_current_datetime()


async def _process_submitted_job(session: AsyncSession, job_model: JobModel):
    # Refetch to load related attributes.
    res = await session.execute(
        select(JobModel)
        .where(JobModel.id == job_model.id)
        .options(joinedload(JobModel.instance))
        .options(joinedload(JobModel.fleet).joinedload(FleetModel.instances))
    )
    job_model = res.unique().scalar_one()
    res = await session.execute(
        select(RunModel)
        .where(RunModel.id == job_model.run_id)
        .options(joinedload(RunModel.project).joinedload(ProjectModel.backends))
        .options(joinedload(RunModel.user).load_only(UserModel.name))
        .options(joinedload(RunModel.fleet).joinedload(FleetModel.instances))
    )
    run_model = res.unique().scalar_one()
    logger.debug("%s: provisioning has started", fmt(job_model))

    project = run_model.project
    run = run_model_to_run(run_model)
    run_spec = run.run_spec
    profile = run_spec.merged_profile
    job = find_job(run.jobs, job_model.replica_num, job_model.job_num)

    # Master job chooses fleet for the run.
    # Due to two-step processing, it's saved to job_model.fleet.
    # Other jobs just inherit fleet from run_model.fleet.
    # If master job chooses no fleet, the new fleet will be created.
    fleet_model = run_model.fleet or job_model.fleet

    master_job = find_job(run.jobs, job_model.replica_num, 0)
    master_job_provisioning_data = None
    if job.job_spec.job_num != 0:
        if master_job.job_submissions[-1].job_provisioning_data is None:
            logger.debug("%s: waiting for master job to be provisioned", fmt(job_model))
            job_model.last_processed_at = common_utils.get_current_datetime()
            await session.commit()
            return
        master_job_provisioning_data = JobProvisioningData.__response__.parse_obj(
            master_job.job_submissions[-1].job_provisioning_data
        )
    if job.job_spec.job_num != 0 or job.job_spec.replica_num != 0:
        if run_model.fleet_id is None:
            logger.debug("%s: waiting for the run to be assigned to the fleet", fmt(job_model))
            job_model.last_processed_at = common_utils.get_current_datetime()
            await session.commit()
            return
    try:
        volume_models = await get_job_configured_volume_models(
            session=session,
            project=project,
            run_spec=run_spec,
            job_num=job.job_spec.job_num,
            job_spec=job.job_spec,
        )
        volumes = await get_job_configured_volumes(
            session=session,
            project=project,
            run_spec=run_spec,
            job_num=job.job_spec.job_num,
            job_spec=job.job_spec,
        )
        check_can_attach_job_volumes(volumes)
    except ServerClientError as e:
        logger.warning("%s: failed to prepare run volumes: %s", fmt(job_model), repr(e))
        job_model.status = JobStatus.TERMINATING
        job_model.termination_reason = JobTerminationReason.VOLUME_ERROR
        job_model.termination_reason_message = e.msg
        job_model.last_processed_at = common_utils.get_current_datetime()
        await session.commit()
        return

    # Submitted jobs processing happens in two steps (transactions).
    # First, the jobs gets an instance assigned (or no instance).
    # Then, the job runs on the assigned instance or a new instance is provisioned.
    # This is needed to avoid holding instances lock for a long time.
    if not job_model.instance_assigned:
        # If another job freed the instance but is still trying to detach volumes,
        # do not provision on it to prevent attaching volumes that are currently detaching.
        detaching_instances_ids = await get_instances_ids_with_detaching_volumes(session)

        fleet_filters = [
            FleetModel.project_id == project.id,
            FleetModel.deleted == False,
        ]
        if run_model.fleet is not None:
            fleet_filters.append(FleetModel.id == run_model.fleet_id)
        if run_spec.merged_profile.fleets is not None:
            fleet_filters.append(FleetModel.name.in_(run_spec.merged_profile.fleets))

        instance_filters = [
            InstanceModel.deleted == False,
            InstanceModel.total_blocks > InstanceModel.busy_blocks,
            InstanceModel.id.not_in(detaching_instances_ids),
        ]

        fleet_models_with_instances, fleet_models_without_instances = await _select_fleet_models(
            session=session,
            fleet_filters=fleet_filters,
            instance_filters=instance_filters,
        )
        instances_ids = sorted(
            itertools.chain.from_iterable(
                [i.id for i in f.instances] for f in fleet_models_with_instances
            )
        )
        if get_db().dialect_name == "sqlite":
            # Start new transaction to see committed changes after lock
            await session.commit()

        async with get_locker(get_db().dialect_name).lock_ctx(
            InstanceModel.__tablename__, instances_ids
        ):
            if get_db().dialect_name == "sqlite":
                fleets_with_instances_ids = [f.id for f in fleet_models_with_instances]
                fleet_models_with_instances = await _refetch_fleet_models_with_instances(
                    session=session,
                    fleets_ids=fleets_with_instances_ids,
                    instances_ids=instances_ids,
                    fleet_filters=fleet_filters,
                    instance_filters=instance_filters,
                )
            fleet_models = fleet_models_with_instances + fleet_models_without_instances
            fleet_model, fleet_instances_with_offers = _find_optimal_fleet_with_offers(
                fleet_models=fleet_models,
                run_model=run_model,
                run_spec=run.run_spec,
                job=job,
                master_job_provisioning_data=master_job_provisioning_data,
                volumes=volumes,
            )
            if fleet_model is None and run_spec.merged_profile.fleets is not None:
                # Run cannot create new fleets when fleets are specified
                logger.debug("%s: failed to use specified fleets", fmt(job_model))
                job_model.status = JobStatus.TERMINATING
                job_model.termination_reason = (
                    JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY
                )
                job_model.last_processed_at = common_utils.get_current_datetime()
                await session.commit()
                return
            instance = await _assign_job_to_fleet_instance(
                session=session,
                instances_with_offers=fleet_instances_with_offers,
                job_model=job_model,
            )
            job_model.fleet = fleet_model
            job_model.instance_assigned = True
            job_model.last_processed_at = common_utils.get_current_datetime()
            if len(instances_ids) > 0:
                await session.commit()
                return
            # If no instances were locked, we can proceed in the same transaction.

    if job_model.instance is not None:
        res = await session.execute(
            select(InstanceModel)
            .where(InstanceModel.id == job_model.instance.id)
            .options(selectinload(InstanceModel.volume_attachments))
            .execution_options(populate_existing=True)
        )
        instance = res.unique().scalar_one()
        job_model.status = JobStatus.PROVISIONING
    else:
        # Assigned no instance, create a new one
        if profile.creation_policy == CreationPolicy.REUSE:
            logger.debug("%s: reuse instance failed", fmt(job_model))
            job_model.status = JobStatus.TERMINATING
            job_model.termination_reason = JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY
            job_model.last_processed_at = common_utils.get_current_datetime()
            await session.commit()
            return

        # Create a new cloud instance
        run_job_result = await _run_job_on_new_instance(
            project=project,
            fleet_model=fleet_model,
            job_model=job_model,
            run=run,
            job=job,
            project_ssh_public_key=project.ssh_public_key,
            project_ssh_private_key=project.ssh_private_key,
            master_job_provisioning_data=master_job_provisioning_data,
            volumes=volumes,
        )
        if run_job_result is None:
            logger.debug("%s: provisioning failed", fmt(job_model))
            job_model.status = JobStatus.TERMINATING
            job_model.termination_reason = JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY
            job_model.last_processed_at = common_utils.get_current_datetime()
            await session.commit()
            return

        logger.info("%s: now is provisioning a new instance", fmt(job_model))
        job_provisioning_data, offer = run_job_result
        job_model.job_provisioning_data = job_provisioning_data.json()
        job_model.status = JobStatus.PROVISIONING
        if fleet_model is None:
            fleet_model = _create_fleet_model_for_job(
                project=project,
                run=run,
            )
        # FIXME: Fleet is not locked which may lead to duplicate instance_num.
        # This is currently hard to fix without locking the fleet for entire provisioning duration.
        # Processing should be done in multiple steps so that
        # InstanceModel is created before provisioning.
        instance_num = await _get_next_instance_num(
            session=session,
            fleet_model=fleet_model,
        )
        instance = _create_instance_model_for_job(
            project=project,
            fleet_model=fleet_model,
            run_spec=run_spec,
            job_model=job_model,
            job=job,
            job_provisioning_data=job_provisioning_data,
            offer=offer,
            instance_num=instance_num,
        )
        job_model.job_runtime_data = _prepare_job_runtime_data(offer).json()
        instance.fleet_id = fleet_model.id
        logger.info(
            "The job %s created the new instance %s",
            job_model.job_name,
            instance.name,
            extra={
                "instance_name": instance.name,
                "instance_status": InstanceStatus.PROVISIONING.value,
            },
        )
        session.add(instance)
        session.add(fleet_model)
        job_model.used_instance_id = instance.id

    volumes_ids = sorted([v.id for vs in volume_models for v in vs])
    # TODO: lock instances for attaching volumes?
    # Take lock to prevent attaching volumes that are to be deleted.
    # If the volume was deleted before the lock, the volume will fail to attach and the job will fail.
    await session.execute(
        select(VolumeModel)
        .where(VolumeModel.id.in_(volumes_ids))
        .options(joinedload(VolumeModel.user).load_only(UserModel.name))
        .order_by(VolumeModel.id)  # take locks in order
        .with_for_update(key_share=True, of=VolumeModel)
    )
    async with get_locker(get_db().dialect_name).lock_ctx(VolumeModel.__tablename__, volumes_ids):
        if len(volume_models) > 0:
            await _attach_volumes(
                session=session,
                project=project,
                job_model=job_model,
                instance=instance,
                volume_models=volume_models,
            )
        job_model.last_processed_at = common_utils.get_current_datetime()
        await session.commit()


async def _select_fleet_models(
    session: AsyncSession, fleet_filters: list, instance_filters: list
) -> tuple[list[FleetModel], list[FleetModel]]:
    # Selecting fleets in two queries since Postgres does not allow
    # locking nullable side of an outer join. So, first lock instances with inner join.
    # Then select left out fleets without instances.
    res = await session.execute(
        select(FleetModel)
        .join(FleetModel.instances)
        .where(*fleet_filters)
        .where(*instance_filters)
        .options(contains_eager(FleetModel.instances))
        .order_by(InstanceModel.id)  # take locks in order
        .with_for_update(key_share=True, of=InstanceModel)
    )
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
        # Load empty list of instances so that downstream code
        # knows this fleet has no instances eligible for offers.
        .options(noload(FleetModel.instances))
    )
    fleet_models_without_instances = list(res.unique().scalars().all())
    return fleet_models_with_instances, fleet_models_without_instances


async def _refetch_fleet_models_with_instances(
    session: AsyncSession,
    fleets_ids: list[uuid.UUID],
    instances_ids: list[uuid.UUID],
    fleet_filters: list,
    instance_filters: list,
) -> list[FleetModel]:
    res = await session.execute(
        select(FleetModel)
        .outerjoin(FleetModel.instances)
        .where(
            FleetModel.id.in_(fleets_ids),
            *fleet_filters,
        )
        .where(
            InstanceModel.id.in_(instances_ids),
            *instance_filters,
        )
        .options(contains_eager(FleetModel.instances))
        .execution_options(populate_existing=True)
    )
    fleet_models = list(res.unique().scalars().all())
    return fleet_models


def _find_optimal_fleet_with_offers(
    fleet_models: list[FleetModel],
    run_model: RunModel,
    run_spec: RunSpec,
    job: Job,
    master_job_provisioning_data: Optional[JobProvisioningData],
    volumes: Optional[list[list[Volume]]],
) -> tuple[Optional[FleetModel], list[tuple[InstanceModel, InstanceOfferWithAvailability]]]:
    if run_model.fleet is not None:
        # Using the fleet that was already chosen by the master job
        fleet_instances_with_offers = _get_fleet_instances_with_offers(
            fleet_model=run_model.fleet,
            run_spec=run_spec,
            job=job,
            master_job_provisioning_data=master_job_provisioning_data,
            volumes=volumes,
        )
        return run_model.fleet, fleet_instances_with_offers

    if len(fleet_models) == 0:
        return None, []

    nodes_required_num = _get_nodes_required_num_for_run(run_spec)
    # The current strategy is to first consider fleets that can accommodate
    # the run without additional provisioning and choose the one with the cheapest offer.
    # Fallback to fleet with the cheapest offer among all fleets with offers.
    candidate_fleets_with_offers: list[
        tuple[
            Optional[FleetModel],
            list[tuple[InstanceModel, InstanceOfferWithAvailability]],
            int,
            tuple[int, float],
        ]
    ] = []
    for candidate_fleet_model in fleet_models:
        fleet_instances_with_offers = _get_fleet_instances_with_offers(
            fleet_model=candidate_fleet_model,
            run_spec=run_spec,
            job=job,
            master_job_provisioning_data=master_job_provisioning_data,
            volumes=volumes,
        )
        fleet_available_offers = [
            o for _, o in fleet_instances_with_offers if o.availability.is_available()
        ]
        fleet_has_available_capacity = nodes_required_num <= len(fleet_available_offers)
        fleet_cheapest_offer = math.inf
        if len(fleet_available_offers) > 0:
            fleet_cheapest_offer = fleet_available_offers[0].price
        fleet_priority = (not fleet_has_available_capacity, fleet_cheapest_offer)
        candidate_fleets_with_offers.append(
            (
                candidate_fleet_model,
                fleet_instances_with_offers,
                len(fleet_available_offers),
                fleet_priority,
            )
        )
    if run_spec.merged_profile.fleets is None and all(
        t[2] == 0 for t in candidate_fleets_with_offers
    ):
        # If fleets are not specified and no fleets have available offers, create a new fleet.
        # This is for compatibility with non-fleet-first UX when runs created new fleets
        # if there are no instances to reuse.
        return None, []
    candidate_fleets_with_offers.sort(key=lambda t: t[-1])
    return candidate_fleets_with_offers[0][:2]


def _get_nodes_required_num_for_run(run_spec: RunSpec) -> int:
    nodes_required_num = 1
    if run_spec.configuration.type == "task":
        nodes_required_num = run_spec.configuration.nodes
    elif (
        run_spec.configuration.type == "service"
        and run_spec.configuration.replicas.min is not None
    ):
        nodes_required_num = run_spec.configuration.replicas.min
    return nodes_required_num


def _get_fleet_instances_with_offers(
    fleet_model: FleetModel,
    run_spec: RunSpec,
    job: Job,
    master_job_provisioning_data: Optional[JobProvisioningData] = None,
    volumes: Optional[List[List[Volume]]] = None,
) -> list[tuple[InstanceModel, InstanceOfferWithAvailability]]:
    pool_instances = fleet_model.instances
    instances_with_offers: list[tuple[InstanceModel, InstanceOfferWithAvailability]]
    profile = run_spec.merged_profile
    multinode = job.job_spec.jobs_per_replica > 1
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


async def _assign_job_to_fleet_instance(
    session: AsyncSession,
    instances_with_offers: list[tuple[InstanceModel, InstanceOfferWithAvailability]],
    job_model: JobModel,
) -> Optional[InstanceModel]:
    if len(instances_with_offers) == 0:
        return None

    instances_with_offers.sort(key=lambda instance_with_offer: instance_with_offer[0].price or 0)
    instance, offer = instances_with_offers[0]
    # Reload InstanceModel with volume attachments
    res = await session.execute(
        select(InstanceModel)
        .where(InstanceModel.id == instance.id)
        .options(joinedload(InstanceModel.volume_attachments))
    )
    instance = res.unique().scalar_one()
    instance.status = InstanceStatus.BUSY
    instance.busy_blocks += offer.blocks

    logger.info(
        "The job %s switched instance %s status to BUSY",
        job_model.job_name,
        instance.name,
        extra={
            "instance_name": instance.name,
            "instance_status": InstanceStatus.BUSY.value,
        },
    )
    logger.info("%s: now is provisioning on '%s'", fmt(job_model), instance.name)
    job_model.instance = instance
    job_model.used_instance_id = instance.id
    job_model.job_provisioning_data = instance.job_provisioning_data
    job_model.job_runtime_data = _prepare_job_runtime_data(offer).json()
    return instance


async def _run_job_on_new_instance(
    project: ProjectModel,
    job_model: JobModel,
    run: Run,
    job: Job,
    project_ssh_public_key: str,
    project_ssh_private_key: str,
    master_job_provisioning_data: Optional[JobProvisioningData] = None,
    volumes: Optional[List[List[Volume]]] = None,
    fleet_model: Optional[FleetModel] = None,
) -> Optional[Tuple[JobProvisioningData, InstanceOfferWithAvailability]]:
    if volumes is None:
        volumes = []
    profile = run.run_spec.merged_profile
    requirements = job.job_spec.requirements
    fleet = None
    if fleet_model is not None:
        fleet = fleet_model_to_fleet(fleet_model)
        if not _check_can_create_new_instance_in_fleet(fleet):
            logger.debug(
                "%s: cannot fit new instance into fleet %s", fmt(job_model), fleet_model.name
            )
            return None
        profile = combine_fleet_and_run_profiles(fleet.spec.merged_profile, profile)
        if profile is None:
            logger.debug("%s: cannot combine fleet %s profile", fmt(job_model), fleet_model.name)
            return None
        fleet_requirements = get_fleet_requirements(fleet.spec)
        requirements = combine_fleet_and_run_requirements(fleet_requirements, requirements)
        if requirements is None:
            logger.debug(
                "%s: cannot combine fleet %s requirements", fmt(job_model), fleet_model.name
            )
            return None
        # TODO: Respect fleet provisioning properties such as tags

    multinode = job.job_spec.jobs_per_replica > 1 or (
        fleet is not None and fleet.spec.configuration.placement == InstanceGroupPlacement.CLUSTER
    )
    offers = await get_offers_by_requirements(
        project=project,
        profile=profile,
        requirements=requirements,
        exclude_not_available=True,
        multinode=multinode,
        master_job_provisioning_data=master_job_provisioning_data,
        volumes=volumes,
        privileged=job.job_spec.privileged,
        instance_mounts=check_run_spec_requires_instance_mounts(run.run_spec),
    )
    # Limit number of offers tried to prevent long-running processing
    # in case all offers fail.
    for backend, offer in offers[: settings.MAX_OFFERS_TRIED]:
        logger.debug(
            "%s: trying %s in %s/%s for $%0.4f per hour",
            fmt(job_model),
            offer.instance.name,
            offer.backend.value,
            offer.region,
            offer.price,
        )
        offer_volumes = _get_offer_volumes(volumes, offer)
        try:
            job_provisioning_data = await common_utils.run_async(
                backend.compute().run_job,
                run,
                job,
                offer,
                project_ssh_public_key,
                project_ssh_private_key,
                offer_volumes,
            )
            return job_provisioning_data, offer
        except BackendError as e:
            logger.warning(
                "%s: %s launch in %s/%s failed: %s",
                fmt(job_model),
                offer.instance.name,
                offer.backend.value,
                offer.region,
                repr(e),
            )
            continue
        except Exception:
            logger.exception(
                "%s: got exception when launching %s in %s/%s",
                fmt(job_model),
                offer.instance.name,
                offer.backend.value,
                offer.region,
            )
            continue
    return None


def _check_can_create_new_instance_in_fleet(fleet: Fleet) -> bool:
    if fleet.spec.configuration.ssh_config is not None:
        return False
    # TODO: Respect nodes.max
    # Ensure concurrent provisioning does not violate nodes.max
    # E.g. lock fleet and split instance model creation
    # and instance provisioning into separate transactions.
    return True


def _create_fleet_model_for_job(
    project: ProjectModel,
    run: Run,
) -> FleetModel:
    placement = InstanceGroupPlacement.ANY
    if run.run_spec.configuration.type == "task" and run.run_spec.configuration.nodes > 1:
        placement = InstanceGroupPlacement.CLUSTER
    spec = FleetSpec(
        configuration=FleetConfiguration(
            name=run.run_spec.run_name,
            placement=placement,
            reservation=run.run_spec.configuration.reservation,
            nodes=Range(min=_get_nodes_required_num_for_run(run.run_spec), max=None),
        ),
        profile=run.run_spec.merged_profile,
        autocreated=True,
    )
    fleet_model = FleetModel(
        id=uuid.uuid4(),
        name=run.run_spec.run_name,
        project=project,
        status=FleetStatus.ACTIVE,
        spec=spec.json(),
        instances=[],
    )
    return fleet_model


async def _get_next_instance_num(session: AsyncSession, fleet_model: FleetModel) -> int:
    res = await session.execute(
        select(func.count(InstanceModel.id)).where(InstanceModel.fleet_id == fleet_model.id)
    )
    instance_count = res.scalar_one()
    return instance_count


def _create_instance_model_for_job(
    project: ProjectModel,
    fleet_model: FleetModel,
    run_spec: RunSpec,
    job_model: JobModel,
    job: Job,
    job_provisioning_data: JobProvisioningData,
    offer: InstanceOfferWithAvailability,
    instance_num: int,
) -> InstanceModel:
    profile = run_spec.merged_profile
    if not job_provisioning_data.dockerized:
        # terminate vastai/k8s instances immediately
        termination_policy = TerminationPolicy.DESTROY_AFTER_IDLE
        termination_idle_time = 0
    else:
        termination_policy, termination_idle_time = get_termination(
            profile, DEFAULT_RUN_TERMINATION_IDLE_TIME
        )
    instance = InstanceModel(
        id=uuid.uuid4(),
        name=f"{fleet_model.name}-{instance_num}",
        instance_num=instance_num,
        project=project,
        created_at=common_utils.get_current_datetime(),
        started_at=common_utils.get_current_datetime(),
        status=InstanceStatus.PROVISIONING,
        unreachable=False,
        job_provisioning_data=job_provisioning_data.json(),
        offer=offer.json(),
        termination_policy=termination_policy,
        termination_idle_time=termination_idle_time,
        jobs=[job_model],
        backend=offer.backend,
        price=offer.price,
        region=offer.region,
        volume_attachments=[],
        total_blocks=1,
        busy_blocks=1,
    )
    return instance


def _prepare_job_runtime_data(offer: InstanceOfferWithAvailability) -> JobRuntimeData:
    if offer.blocks == offer.total_blocks:
        if env_utils.get_bool("DSTACK_FORCE_BRIDGE_NETWORK"):
            network_mode = NetworkMode.BRIDGE
        else:
            network_mode = NetworkMode.HOST
        return JobRuntimeData(
            network_mode=network_mode,
            offer=offer,
        )
    return JobRuntimeData(
        network_mode=NetworkMode.BRIDGE,
        offer=offer,
        cpu=offer.instance.resources.cpus,
        gpu=len(offer.instance.resources.gpus),
        memory=Memory(offer.instance.resources.memory_mib / 1024),
    )


def _get_offer_volumes(
    volumes: List[List[Volume]],
    offer: InstanceOfferWithAvailability,
) -> List[Volume]:
    """
    Returns volumes suitable for the offer for each mount point.
    """
    offer_volumes = []
    for mount_point_volumes in volumes:
        offer_volumes.append(_get_offer_mount_point_volume(mount_point_volumes, offer))
    return offer_volumes


def _get_offer_mount_point_volume(
    volumes: List[Volume],
    offer: InstanceOfferWithAvailability,
) -> Volume:
    """
    Returns the first suitable volume for the offer among possible mount point volumes.
    """
    for volume in volumes:
        if (
            volume.configuration.backend != offer.backend
            or volume.configuration.region.lower() != offer.region.lower()
        ):
            continue
        return volume
    raise ServerClientError("Failed to find an eligible volume for the mount point")


async def _attach_volumes(
    session: AsyncSession,
    project: ProjectModel,
    job_model: JobModel,
    instance: InstanceModel,
    volume_models: List[List[VolumeModel]],
):
    job_provisioning_data = common_utils.get_or_error(get_instance_provisioning_data(instance))
    backend = await get_project_backend_by_type_or_error(
        project=project,
        backend_type=job_provisioning_data.backend,
    )
    job_runtime_data = common_utils.get_or_error(get_job_runtime_data(job_model))
    job_runtime_data.volume_names = []
    logger.info("Attaching volumes: %s", [[v.name for v in vs] for vs in volume_models])
    for mount_point_volume_models in volume_models:
        for volume_model in mount_point_volume_models:
            volume = volume_model_to_volume(volume_model)
            try:
                if (
                    job_provisioning_data.get_base_backend() != volume.configuration.backend
                    or job_provisioning_data.region.lower() != volume.configuration.region.lower()
                ):
                    continue
                if volume.provisioning_data is not None and volume.provisioning_data.attachable:
                    await _attach_volume(
                        session=session,
                        backend=backend,
                        volume_model=volume_model,
                        instance=instance,
                        jpd=job_provisioning_data,
                    )
                    job_runtime_data.volume_names.append(volume.name)
                    break  # attach next mount point
            except (ServerClientError, BackendError) as e:
                logger.warning("%s: failed to attached volume: %s", fmt(job_model), repr(e))
                job_model.status = JobStatus.TERMINATING
                job_model.termination_reason = JobTerminationReason.VOLUME_ERROR
                job_model.termination_reason_message = "Failed to attach volume"
            except Exception:
                logger.exception(
                    "%s: got exception when attaching volume",
                    fmt(job_model),
                )
                job_model.status = JobStatus.TERMINATING
                job_model.termination_reason = JobTerminationReason.VOLUME_ERROR
                job_model.termination_reason_message = "Failed to attach volume"
            finally:
                job_model.job_runtime_data = job_runtime_data.json()


async def _attach_volume(
    session: AsyncSession,
    backend: Backend,
    volume_model: VolumeModel,
    instance: InstanceModel,
    jpd: JobProvisioningData,
):
    compute = backend.compute()
    assert isinstance(compute, ComputeWithVolumeSupport)
    volume = volume_model_to_volume(volume_model)
    # Refresh only to check if the volume wasn't deleted before the lock
    await session.refresh(volume_model)
    if volume_model.deleted:
        raise ServerClientError("Cannot attach a deleted volume")
    attachment_data = await common_utils.run_async(
        compute.attach_volume,
        volume=volume,
        provisioning_data=jpd,
    )
    volume_attachment_model = VolumeAttachmentModel(
        volume=volume_model,
        attachment_data=attachment_data.json(),
    )
    instance.volume_attachments.append(volume_attachment_model)

    volume_model.last_job_processed_at = common_utils.get_current_datetime()
