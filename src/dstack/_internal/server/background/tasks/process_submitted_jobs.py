import asyncio
import itertools
import uuid
from contextlib import AsyncExitStack
from datetime import datetime, timedelta
from typing import List, Optional, Union

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager, joinedload, load_only, noload, selectinload

from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.base.compute import (
    ComputeWithGroupProvisioningSupport,
    ComputeWithPlacementGroupSupport,
    ComputeWithVolumeSupport,
)
from dstack._internal.core.backends.base.models import JobConfiguration
from dstack._internal.core.backends.features import (
    BACKENDS_WITH_GROUP_PROVISIONING_SUPPORT,
    BACKENDS_WITH_PLACEMENT_GROUPS_SUPPORT,
)
from dstack._internal.core.errors import BackendError, ServerClientError
from dstack._internal.core.models.common import NetworkMode
from dstack._internal.core.models.compute_groups import ComputeGroupProvisioningData
from dstack._internal.core.models.fleets import (
    FleetConfiguration,
    FleetNodesSpec,
    FleetSpec,
    FleetStatus,
    InstanceGroupPlacement,
)
from dstack._internal.core.models.instances import InstanceOfferWithAvailability, InstanceStatus
from dstack._internal.core.models.profiles import (
    DEFAULT_RUN_TERMINATION_IDLE_TIME,
    CreationPolicy,
    Profile,
    TerminationPolicy,
)
from dstack._internal.core.models.resources import Memory
from dstack._internal.core.models.runs import (
    Job,
    JobProvisioningData,
    JobRuntimeData,
    JobStatus,
    JobTerminationReason,
    Requirements,
    Run,
)
from dstack._internal.core.models.volumes import Volume
from dstack._internal.core.services.profiles import get_termination
from dstack._internal.server import settings
from dstack._internal.server.background.tasks.process_compute_groups import ComputeGroupStatus
from dstack._internal.server.db import (
    get_db,
    get_session_ctx,
    is_db_postgres,
    is_db_sqlite,
    sqlite_commit,
)
from dstack._internal.server.models import (
    ComputeGroupModel,
    FleetModel,
    InstanceModel,
    JobModel,
    ProjectModel,
    RunModel,
    UserModel,
    VolumeAttachmentModel,
    VolumeModel,
)
from dstack._internal.server.services import events
from dstack._internal.server.services.backends import get_project_backend_by_type_or_error
from dstack._internal.server.services.fleets import (
    check_can_create_new_cloud_instance_in_fleet,
    fleet_model_to_fleet,
    generate_fleet_name,
    get_fleet_master_instance_provisioning_data,
    get_next_instance_num,
    is_cloud_cluster,
)
from dstack._internal.server.services.instances import (
    format_instance_status_for_event,
    get_instance_provisioning_data,
)
from dstack._internal.server.services.jobs import (
    check_can_attach_job_volumes,
    find_job,
    find_jobs,
    get_job_configured_volume_models,
    get_job_configured_volumes,
    get_job_runtime_data,
    is_master_job,
    is_multinode_job,
    switch_job_status,
)
from dstack._internal.server.services.locking import get_locker, string_to_lock_id
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.offers import get_offers_by_requirements
from dstack._internal.server.services.placement import (
    find_or_create_suitable_placement_group,
    get_fleet_placement_group_models,
    get_placement_group_model_for_job,
    placement_group_model_to_placement_group_optional,
    schedule_fleet_placement_groups_deletion,
)
from dstack._internal.server.services.runs import (
    run_model_to_run,
)
from dstack._internal.server.services.runs.plan import (
    find_optimal_fleet_with_offers,
    get_run_candidate_fleet_models_filters,
    get_run_profile_and_requirements_in_fleet,
    select_run_candidate_fleet_models_with_filters,
)
from dstack._internal.server.services.runs.spec import (
    check_run_spec_requires_instance_mounts,
    get_nodes_required_num,
)
from dstack._internal.server.services.volumes import (
    volume_model_to_volume,
)
from dstack._internal.server.utils import sentry_utils
from dstack._internal.settings import FeatureFlags
from dstack._internal.utils import common as common_utils
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
                    JobModel.waiting_master_job.is_not(True),
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
            async with AsyncExitStack() as exit_stack:
                await _process_submitted_job(
                    exit_stack=exit_stack,
                    session=session,
                    job_model=job_model,
                )
        finally:
            lockset.difference_update([job_model_id])
        global last_processed_at
        last_processed_at = common_utils.get_current_datetime()


async def _process_submitted_job(
    exit_stack: AsyncExitStack, session: AsyncSession, job_model: JobModel
):
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
    run_profile = run_spec.merged_profile
    job = find_job(run.jobs, job_model.replica_num, job_model.job_num)
    replica_jobs = find_jobs(run.jobs, replica_num=job_model.replica_num)
    replica_job_models = _get_job_models_for_jobs(run_model.jobs, replica_jobs)
    multinode = job.job_spec.jobs_per_replica > 1

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
        job_model.termination_reason = JobTerminationReason.VOLUME_ERROR
        job_model.termination_reason_message = e.msg
        switch_job_status(session, job_model, JobStatus.TERMINATING)
        job_model.last_processed_at = common_utils.get_current_datetime()
        await session.commit()
        return

    # Submitted jobs processing happens in two steps (transactions).
    # First, the jobs gets an instance assigned (or no instance).
    # Then, the job runs on the assigned instance or a new instance is provisioned.
    # This is needed to avoid holding instances lock for a long time.
    if not job_model.instance_assigned:
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
            lock_instances=True,
        )
        instances_ids = sorted(
            itertools.chain.from_iterable(
                [i.id for i in f.instances] for f in fleet_models_with_instances
            )
        )
        await sqlite_commit(session)
        await exit_stack.enter_async_context(
            get_locker(get_db().dialect_name).lock_ctx(InstanceModel.__tablename__, instances_ids)
        )
        if is_db_sqlite():
            fleets_with_instances_ids = [f.id for f in fleet_models_with_instances]
            fleet_models_with_instances = await _refetch_fleet_models_with_instances(
                session=session,
                fleets_ids=fleets_with_instances_ids,
                instances_ids=instances_ids,
                fleet_filters=fleet_filters,
                instance_filters=instance_filters,
            )
        fleet_models = fleet_models_with_instances + fleet_models_without_instances
        fleet_model, fleet_instances_with_offers, _ = await find_optimal_fleet_with_offers(
            project=project,
            fleet_models=fleet_models,
            run_model=run_model,
            run_spec=run.run_spec,
            job=job,
            master_job_provisioning_data=master_job_provisioning_data,
            volumes=volumes,
            exclude_not_available=True,
        )
        if fleet_model is None:
            if run_spec.merged_profile.fleets is not None:
                # Run cannot create new fleets when fleets are specified
                logger.debug("%s: failed to use specified fleets", fmt(job_model))
                job_model.termination_reason = (
                    JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY
                )
                job_model.termination_reason_message = "Failed to use specified fleets"
                switch_job_status(session, job_model, JobStatus.TERMINATING)
                job_model.last_processed_at = common_utils.get_current_datetime()
                await session.commit()
                return
            if not FeatureFlags.AUTOCREATED_FLEETS_ENABLED:
                logger.debug("%s: no fleet found", fmt(job_model))
                job_model.termination_reason = (
                    JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY
                )
                # Note: `_get_job_status_message` relies on the "No fleet found" substring to return "no fleets"
                job_model.termination_reason_message = (
                    "No matching fleet found. Possible reasons: "
                    "https://dstack.ai/docs/guides/troubleshooting/#no-fleets"
                )
                switch_job_status(session, job_model, JobStatus.TERMINATING)
                job_model.last_processed_at = common_utils.get_current_datetime()
                await session.commit()
                return
        instance = await _assign_job_to_fleet_instance(
            session=session,
            fleet_model=fleet_model,
            instances_with_offers=fleet_instances_with_offers,
            job_model=job_model,
            multinode=multinode,
        )
        job_model.last_processed_at = common_utils.get_current_datetime()
        await session.commit()
        return

    jobs_to_provision = _get_jobs_to_provision(job, replica_jobs, job_model)
    # TODO: Volume attachment for compute groups is not yet supported since
    # currently supported compute groups (e.g. Runpod) don't need explicit volume attachment.
    need_volume_attachment = True

    if job_model.instance is not None:
        res = await session.execute(
            select(InstanceModel)
            .where(InstanceModel.id == job_model.instance.id)
            .options(selectinload(InstanceModel.volume_attachments))
            .execution_options(populate_existing=True)
        )
        instance = res.unique().scalar_one()
        switch_job_status(session, job_model, JobStatus.PROVISIONING)
    else:
        if run_profile.creation_policy == CreationPolicy.REUSE:
            logger.debug("%s: reuse instance failed", fmt(job_model))
            job_model.termination_reason = JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY
            job_model.termination_reason_message = "Could not reuse any instances for this job"
            switch_job_status(session, job_model, JobStatus.TERMINATING)
            job_model.last_processed_at = common_utils.get_current_datetime()
            await session.commit()
            return

        master_instance_provisioning_data = (
            await _fetch_fleet_with_master_instance_provisioning_data(
                exit_stack=exit_stack,
                session=session,
                fleet_model=fleet_model,
                job=job,
            )
        )
        master_provisioning_data = (
            master_job_provisioning_data or master_instance_provisioning_data
        )
        run_job_result = await _run_jobs_on_new_instances(
            session=session,
            project=project,
            fleet_model=fleet_model,
            job_model=job_model,
            run=run,
            jobs=jobs_to_provision,
            project_ssh_public_key=project.ssh_public_key,
            project_ssh_private_key=project.ssh_private_key,
            master_job_provisioning_data=master_provisioning_data,
            volumes=volumes,
        )
        if run_job_result is None:
            logger.debug("%s: provisioning failed", fmt(job_model))
            job_model.termination_reason = JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY
            switch_job_status(session, job_model, JobStatus.TERMINATING)
            job_model.last_processed_at = common_utils.get_current_datetime()
            await session.commit()
            return

        if fleet_model is None:
            fleet_model = await _create_fleet_model_for_job(
                exit_stack=exit_stack,
                session=session,
                project=project,
                run=run,
            )
            session.add(fleet_model)
            events.emit(
                session,
                f"Fleet created for job. Fleet status: {fleet_model.status.upper()}",
                actor=events.SystemActor(),
                targets=[
                    events.Target.from_model(fleet_model),
                    events.Target.from_model(job_model),
                ],
            )

        provisioning_data, offer, effective_profile, _ = run_job_result
        compute_group_model = None
        if isinstance(provisioning_data, ComputeGroupProvisioningData):
            need_volume_attachment = False
            provisioned_jobs = jobs_to_provision
            jpds = provisioning_data.job_provisioning_datas
            compute_group_model = ComputeGroupModel(
                id=uuid.uuid4(),
                project=project,
                fleet=fleet_model,
                status=ComputeGroupStatus.RUNNING,
                provisioning_data=provisioning_data.json(),
            )
            session.add(compute_group_model)
        else:
            provisioned_jobs = [job]
            jpds = [provisioning_data]

        logger.info("%s: provisioned %s new instance(s)", fmt(job_model), len(provisioned_jobs))
        provisioned_job_models = _get_job_models_for_jobs(run_model.jobs, provisioned_jobs)
        instance = None  # Instance for attaching volumes in case of single job provisioned
        for provisioned_job_model, jpd in zip(provisioned_job_models, jpds):
            provisioned_job_model.job_provisioning_data = jpd.json()
            switch_job_status(session, provisioned_job_model, JobStatus.PROVISIONING)
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
                compute_group_model=compute_group_model,
                job_model=provisioned_job_model,
                job_provisioning_data=jpd,
                offer=offer,
                instance_num=instance_num,
                profile=effective_profile,
            )
            provisioned_job_model.job_runtime_data = _prepare_job_runtime_data(
                offer, multinode
            ).json()
            session.add(instance)
            events.emit(
                session,
                f"Instance created for job. Instance status: {format_instance_status_for_event(instance)}",
                actor=events.SystemActor(),
                targets=[
                    events.Target.from_model(instance),
                    events.Target.from_model(provisioned_job_model),
                ],
            )
            provisioned_job_model.used_instance_id = instance.id
            provisioned_job_model.last_processed_at = common_utils.get_current_datetime()

    _allow_other_replica_jobs_to_provision(job_model, replica_job_models, jobs_to_provision)

    volumes_ids = sorted([v.id for vs in volume_models for v in vs])
    if need_volume_attachment:
        # Take lock to prevent attaching volumes that are to be deleted.
        # If the volume was deleted before the lock, the volume will fail to attach and the job will fail.
        # TODO: Lock instances for attaching volumes?
        await session.execute(
            select(VolumeModel)
            .where(VolumeModel.id.in_(volumes_ids))
            .options(joinedload(VolumeModel.user).load_only(UserModel.name))
            .order_by(VolumeModel.id)  # take locks in order
            .with_for_update(key_share=True, of=VolumeModel)
        )
        await exit_stack.enter_async_context(
            get_locker(get_db().dialect_name).lock_ctx(VolumeModel.__tablename__, volumes_ids)
        )
        if len(volume_models) > 0:
            assert instance is not None
            await _attach_volumes(
                session=session,
                project=project,
                job_model=job_model,
                instance=instance,
                volume_models=volume_models,
            )
    await session.commit()


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
    )
    fleet_models = list(res.unique().scalars().all())
    return fleet_models


async def _fetch_fleet_with_master_instance_provisioning_data(
    exit_stack: AsyncExitStack,
    session: AsyncSession,
    fleet_model: Optional[FleetModel],
    job: Job,
) -> Optional[JobProvisioningData]:
    master_instance_provisioning_data = None
    if is_master_job(job) and fleet_model is not None:
        fleet = fleet_model_to_fleet(fleet_model)
        if fleet.spec.configuration.placement == InstanceGroupPlacement.CLUSTER:
            # To avoid violating fleet placement cluster during master provisioning,
            # we must lock empty fleets and respect existing instances in non-empty fleets.
            # On SQLite always take the lock during master provisioning for simplicity.
            await exit_stack.enter_async_context(
                get_locker(get_db().dialect_name).lock_ctx(
                    FleetModel.__tablename__, [fleet_model.id]
                )
            )
            await sqlite_commit(session)
            res = await session.execute(
                select(FleetModel)
                .outerjoin(FleetModel.instances)
                .where(
                    FleetModel.id == fleet_model.id,
                    or_(
                        InstanceModel.id.is_(None),
                        InstanceModel.deleted == True,
                    ),
                )
                .with_for_update(key_share=True, of=FleetModel)
                .execution_options(populate_existing=True)
                .options(noload(FleetModel.instances))
            )
            empty_fleet_model = res.unique().scalar()
            if empty_fleet_model is not None:
                fleet_model = empty_fleet_model
            else:
                res = await session.execute(
                    select(FleetModel)
                    .join(FleetModel.instances)
                    .where(
                        FleetModel.id == fleet_model.id,
                        InstanceModel.deleted == False,
                    )
                    .options(contains_eager(FleetModel.instances))
                    .execution_options(populate_existing=True)
                )
                fleet_model = res.unique().scalar_one()
            master_instance_provisioning_data = get_fleet_master_instance_provisioning_data(
                fleet_model=fleet_model,
                fleet_spec=fleet.spec,
            )
    return master_instance_provisioning_data


async def _assign_job_to_fleet_instance(
    session: AsyncSession,
    fleet_model: Optional[FleetModel],
    job_model: JobModel,
    instances_with_offers: list[tuple[InstanceModel, InstanceOfferWithAvailability]],
    multinode: bool,
) -> Optional[InstanceModel]:
    job_model.fleet = fleet_model
    job_model.instance_assigned = True
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

    job_model.instance = instance
    job_model.used_instance_id = instance.id
    job_model.job_provisioning_data = instance.job_provisioning_data
    job_model.job_runtime_data = _prepare_job_runtime_data(offer, multinode).json()
    events.emit(
        session,
        (
            "Job assigned to instance."
            f" Instance status: {format_instance_status_for_event(instance)}"
        ),
        actor=events.SystemActor(),
        targets=[
            events.Target.from_model(job_model),
            events.Target.from_model(instance),
        ],
    )
    return instance


def _get_jobs_to_provision(job: Job, replica_jobs: list[Job], job_model: JobModel) -> list[Job]:
    """
    Returns the passed job for non-master jobs and all replica jobs for master jobs in multinode setups.
    """
    jobs_to_provision = [job]
    if (
        is_multinode_job(job)
        and is_master_job(job)
        # job_model.waiting_master_job is not set for legacy jobs.
        # In this case compute group provisioning not supported
        # and jobs always provision one-by-one.
        and job_model.waiting_master_job is not None
    ):
        jobs_to_provision = replica_jobs
    return jobs_to_provision


def _allow_other_replica_jobs_to_provision(
    job_model: JobModel,
    replica_job_models: list[JobModel],
    jobs_to_provision: list[Job],
):
    if len(jobs_to_provision) > 1:
        logger.debug("%s: allow replica jobs to be provisioned one-by-one", fmt(job_model))
        for replica_job_model in replica_job_models:
            replica_job_model.waiting_master_job = False


async def _run_jobs_on_new_instances(
    session: AsyncSession,
    project: ProjectModel,
    job_model: JobModel,
    run: Run,
    jobs: list[Job],
    project_ssh_public_key: str,
    project_ssh_private_key: str,
    master_job_provisioning_data: Optional[JobProvisioningData] = None,
    volumes: Optional[list[list[Volume]]] = None,
    fleet_model: Optional[FleetModel] = None,
) -> Optional[
    tuple[
        Union[JobProvisioningData, ComputeGroupProvisioningData],
        InstanceOfferWithAvailability,
        Profile,
        Requirements,
    ]
]:
    """
    Provisions an instance for a job or a compute group for multiple jobs and runs the jobs.
    Even when multiple jobs are passes, it may still provision only one instance
    and run only the master job in case there are no offers supporting cluster groups.
    Other jobs should be provisioned one-by-one later.
    """
    if volumes is None:
        volumes = []
    job = jobs[0]
    profile = run.run_spec.merged_profile
    requirements = job.job_spec.requirements
    fleet = None
    if fleet_model is not None:
        fleet = fleet_model_to_fleet(fleet_model)
        try:
            check_can_create_new_cloud_instance_in_fleet(fleet)
            profile, requirements = get_run_profile_and_requirements_in_fleet(
                job=job,
                run_spec=run.run_spec,
                fleet=fleet,
            )
        except ValueError as e:
            logger.debug("%s: %s", fmt(job_model), e.args[0])
            return None
        # TODO: Respect fleet provisioning properties such as tags

    # The placement group is determined when provisioning the master instance
    # and used for all other instances in the fleet.
    placement_group_models = await get_fleet_placement_group_models(
        session=session,
        fleet_id=fleet_model.id if fleet_model else None,
    )
    placement_group_model = get_placement_group_model_for_job(
        placement_group_models=placement_group_models,
        fleet_model=fleet_model,
    )
    multinode = requirements.multinode or is_multinode_job(job)
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
        placement_group=placement_group_model_to_placement_group_optional(placement_group_model),
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
        job_configurations = [JobConfiguration(job=j, volumes=offer_volumes) for j in jobs]
        compute = backend.compute()
        if (
            fleet_model is not None
            and len(fleet_model.instances) == 0
            and is_cloud_cluster(fleet_model)
            and offer.backend in BACKENDS_WITH_PLACEMENT_GROUPS_SUPPORT
            and isinstance(compute, ComputeWithPlacementGroupSupport)
            and (
                compute.are_placement_groups_compatible_with_reservations(offer.backend)
                or job.job_spec.requirements.reservation is None
            )
        ):
            placement_group_model = await find_or_create_suitable_placement_group(
                fleet_model=fleet_model,
                placement_groups=placement_group_models,
                instance_offer=offer,
                compute=compute,
            )
            if placement_group_model is None:  # error occurred
                continue
            session.add(placement_group_model)
            placement_group_models.append(placement_group_model)
        try:
            if len(jobs) > 1 and offer.backend in BACKENDS_WITH_GROUP_PROVISIONING_SUPPORT:
                assert isinstance(compute, ComputeWithGroupProvisioningSupport)
                cgpd = await common_utils.run_async(
                    compute.run_jobs,
                    run,
                    job_configurations,
                    offer,
                    project_ssh_public_key,
                    project_ssh_private_key,
                    placement_group_model_to_placement_group_optional(placement_group_model),
                )
                return cgpd, offer, profile, requirements
            else:
                jpd = await common_utils.run_async(
                    compute.run_job,
                    run,
                    job,
                    offer,
                    project_ssh_public_key,
                    project_ssh_private_key,
                    offer_volumes,
                    placement_group_model_to_placement_group_optional(placement_group_model),
                )
                return jpd, offer, profile, requirements
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
        finally:
            if fleet_model is not None and len(fleet_model.instances) == 0:
                # Clean up placement groups that did not end up being used.
                # Flush to update still uncommitted placement groups.
                await session.flush()
                await schedule_fleet_placement_groups_deletion(
                    session=session,
                    fleet_id=fleet_model.id,
                    except_placement_group_ids=(
                        [placement_group_model.id] if placement_group_model is not None else []
                    ),
                )
    return None


async def _create_fleet_model_for_job(
    exit_stack: AsyncExitStack,
    session: AsyncSession,
    project: ProjectModel,
    run: Run,
) -> FleetModel:
    placement = InstanceGroupPlacement.ANY
    if run.run_spec.configuration.type == "task" and run.run_spec.configuration.nodes > 1:
        placement = InstanceGroupPlacement.CLUSTER
    nodes = get_nodes_required_num(run.run_spec)
    lock_namespace = f"fleet_names_{project.name}"
    if is_db_sqlite():
        # Start new transaction to see committed changes after lock
        await session.commit()
    elif is_db_postgres():
        await session.execute(
            select(func.pg_advisory_xact_lock(string_to_lock_id(lock_namespace)))
        )
    await exit_stack.enter_async_context(
        get_locker(get_db().dialect_name).get_lockset(lock_namespace)[0]
    )
    fleet_name = await generate_fleet_name(session=session, project=project)
    spec = FleetSpec(
        configuration=FleetConfiguration(
            name=fleet_name,
            placement=placement,
            reservation=run.run_spec.configuration.reservation,
            nodes=FleetNodesSpec(
                min=nodes,
                target=nodes,
                max=None,
            ),
        ),
        profile=run.run_spec.merged_profile,
        autocreated=True,
    )
    fleet_model = FleetModel(
        id=uuid.uuid4(),
        name=fleet_name,
        project=project,
        status=FleetStatus.ACTIVE,
        spec=spec.json(),
        instances=[],
    )
    return fleet_model


async def _get_next_instance_num(session: AsyncSession, fleet_model: FleetModel) -> int:
    res = await session.execute(
        select(InstanceModel.instance_num).where(
            InstanceModel.fleet_id == fleet_model.id,
            InstanceModel.deleted.is_(False),
        )
    )
    taken_instance_nums = set(res.scalars().all())
    return get_next_instance_num(taken_instance_nums)


def _create_instance_model_for_job(
    project: ProjectModel,
    fleet_model: FleetModel,
    compute_group_model: Optional[ComputeGroupModel],
    job_model: JobModel,
    job_provisioning_data: JobProvisioningData,
    offer: InstanceOfferWithAvailability,
    instance_num: int,
    profile: Profile,
) -> InstanceModel:
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
        fleet=fleet_model,
        compute_group=compute_group_model,
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


def _prepare_job_runtime_data(
    offer: InstanceOfferWithAvailability, multinode: bool
) -> JobRuntimeData:
    if offer.blocks == offer.total_blocks:
        if settings.JOB_NETWORK_MODE == settings.JobNetworkMode.FORCED_BRIDGE:
            network_mode = NetworkMode.BRIDGE
        elif settings.JOB_NETWORK_MODE == settings.JobNetworkMode.HOST_WHEN_POSSIBLE:
            network_mode = NetworkMode.HOST
        else:
            assert settings.JOB_NETWORK_MODE == settings.JobNetworkMode.HOST_FOR_MULTINODE_ONLY
            network_mode = NetworkMode.HOST if multinode else NetworkMode.BRIDGE
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
                job_model.termination_reason = JobTerminationReason.VOLUME_ERROR
                job_model.termination_reason_message = "Failed to attach volume"
                switch_job_status(session, job_model, JobStatus.TERMINATING)
            except Exception:
                logger.exception(
                    "%s: got exception when attaching volume",
                    fmt(job_model),
                )
                job_model.termination_reason = JobTerminationReason.VOLUME_ERROR
                job_model.termination_reason_message = "Failed to attach volume"
                switch_job_status(session, job_model, JobStatus.TERMINATING)
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


def _get_job_models_for_jobs(
    job_models: list[JobModel],
    jobs: list[Job],
) -> list[JobModel]:
    """
    Returns job models of latest submissions for a list of jobs.
    Preserves jobs order.
    """
    id_to_job_model_map = {jm.id: jm for jm in job_models}
    return [id_to_job_model_map[j.job_submissions[-1].id] for j in jobs]
