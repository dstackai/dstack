import uuid
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.backends.base import Backend
from dstack._internal.core.errors import BackendError, ServerClientError
from dstack._internal.core.models.fleets import (
    FleetConfiguration,
    FleetSpec,
    FleetStatus,
    InstanceGroupPlacement,
)
from dstack._internal.core.models.instances import (
    InstanceOfferWithAvailability,
    InstanceStatus,
)
from dstack._internal.core.models.profiles import (
    CreationPolicy,
    TerminationPolicy,
)
from dstack._internal.core.models.runs import (
    Job,
    JobProvisioningData,
    JobStatus,
    JobTerminationReason,
    Run,
    RunSpec,
)
from dstack._internal.core.models.volumes import Volume
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import (
    FleetModel,
    InstanceModel,
    JobModel,
    PoolModel,
    ProjectModel,
    RunModel,
    VolumeModel,
)
from dstack._internal.server.services.backends import get_project_backend_by_type_or_error
from dstack._internal.server.services.fleets import (
    PROCESSING_FLEETS_IDS,
    PROCESSING_FLEETS_LOCK,
    fleet_model_to_fleet,
)
from dstack._internal.server.services.jobs import (
    PROCESSING_INSTANCES_LOCK,
    SUBMITTED_PROCESSING_JOBS_IDS,
    SUBMITTED_PROCESSING_JOBS_LOCK,
    find_job,
)
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.pools import (
    filter_pool_instances,
    get_or_create_pool_by_name,
    get_pool_instances,
)
from dstack._internal.server.services.runs import (
    PROCESSING_RUNS_IDS,
    PROCESSING_RUNS_LOCK,
    check_can_attach_run_volumes,
    get_offers_by_requirements,
    get_run_volume_models,
    run_model_to_run,
)
from dstack._internal.server.services.volumes import (
    PROCESSING_VOLUMES_IDS,
    PROCESSING_VOLUMES_LOCK,
    volume_model_to_volume,
)
from dstack._internal.server.utils.common import run_async, wait_to_lock, wait_to_lock_many
from dstack._internal.utils import common as common_utils
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def process_submitted_jobs():
    async with get_session_ctx() as session:
        async with PROCESSING_RUNS_LOCK, SUBMITTED_PROCESSING_JOBS_LOCK:
            res = await session.execute(
                select(JobModel)
                .where(
                    JobModel.status == JobStatus.SUBMITTED,
                    JobModel.id.not_in(SUBMITTED_PROCESSING_JOBS_IDS),
                    JobModel.run_id.not_in(PROCESSING_RUNS_IDS),
                )
                .order_by(JobModel.last_processed_at.asc())
                .limit(1)  # TODO process multiple at once
            )
            job_model = res.scalar()
            if job_model is None:
                return

            SUBMITTED_PROCESSING_JOBS_IDS.add(job_model.id)

    try:
        job_model_id = job_model.id
        await _process_job(job_id=job_model_id)
    finally:
        SUBMITTED_PROCESSING_JOBS_IDS.remove(job_model_id)


async def _process_job(job_id: UUID):
    async with get_session_ctx() as session:
        res = await session.execute(select(JobModel).where(JobModel.id == job_id))
        job_model = res.scalar_one()
        await _process_submitted_job(
            session=session,
            job_model=job_model,
        )


async def _process_submitted_job(session: AsyncSession, job_model: JobModel):
    logger.debug("%s: provisioning has started", fmt(job_model))
    res = await session.execute(
        select(RunModel)
        .where(RunModel.id == job_model.run_id)
        .options(joinedload(RunModel.project).joinedload(ProjectModel.backends))
        .options(joinedload(RunModel.user))
        .options(joinedload(RunModel.fleet).joinedload(FleetModel.instances))
    )
    run_model = res.unique().scalar_one()
    project = run_model.project
    run_spec = RunSpec.__response__.parse_raw(run_model.run_spec)
    profile = run_spec.merged_profile

    run = run_model_to_run(run_model)
    job = find_job(run.jobs, job_model.replica_num, job_model.job_num)

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
        volume_models = await get_run_volume_models(
            session=session,
            project=project,
            run_spec=run_spec,
        )
        volumes = [volume_model_to_volume(v) for v in volume_models]
        check_can_attach_run_volumes(run_spec=run_spec, volumes=volumes)
    except ServerClientError as e:
        logger.error("%s: ", fmt(job_model))
        job_model.status = JobStatus.TERMINATING
        # TODO: Replace with JobTerminationReason.VOLUME_ERROR in 0.19
        job_model.termination_reason = JobTerminationReason.TERMINATED_BY_SERVER
        job_model.termination_reason_message = e.msg
        job_model.last_processed_at = common_utils.get_current_datetime()
        await session.commit()
        return

    # Try to provision on an instance from the pool
    pool = await get_or_create_pool_by_name(
        session=session,
        project=project,
        pool_name=profile.pool_name,
    )
    instance = await _run_job_on_pool_instance(
        session=session,
        pool=pool,
        run_spec=run_spec,
        job_model=job_model,
        job=job,
        fleet_model=run_model.fleet,
        master_job_provisioning_data=master_job_provisioning_data,
        volumes=volumes,
    )
    if instance is None:
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
            fleet_model=run_model.fleet,
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
        fleet_model = _get_or_create_fleet_model_for_job(
            project=project,
            run_model=run_model,
            run=run,
        )
        instance_num = await _get_next_instance_num(
            session=session,
            fleet_model=fleet_model,
        )
        instance = _create_instance_model_for_job(
            project=project,
            pool=pool,
            fleet_model=fleet_model,
            run_spec=run_spec,
            job_model=job_model,
            job=job,
            job_provisioning_data=job_provisioning_data,
            offer=offer,
            instance_num=instance_num,
        )
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
        await session.flush()  # to get im.id
        job_model.used_instance_id = instance.id

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


async def _run_job_on_pool_instance(
    session: AsyncSession,
    pool: PoolModel,
    run_spec: RunSpec,
    job_model: JobModel,
    job: Job,
    fleet_model: Optional[FleetModel],
    master_job_provisioning_data: Optional[JobProvisioningData] = None,
    volumes: Optional[List[Volume]] = None,
) -> Optional[InstanceModel]:
    profile = run_spec.merged_profile
    async with PROCESSING_INSTANCES_LOCK:
        relevant_instances = filter_pool_instances(
            pool_instances=get_pool_instances(pool),
            profile=profile,
            requirements=job.job_spec.requirements,
            status=InstanceStatus.IDLE,
            fleet_model=fleet_model,
            multinode=job.job_spec.jobs_per_replica > 1,
            master_job_provisioning_data=master_job_provisioning_data,
            volumes=volumes,
        )
        if len(relevant_instances) == 0:
            return None
        sorted_instances = sorted(relevant_instances, key=lambda instance: instance.price)
        instance = sorted_instances[0]
        # Reload InstanceModel with volumes
        res = await session.execute(
            select(InstanceModel)
            .where(InstanceModel.id == instance.id)
            .options(joinedload(InstanceModel.volumes))
        )
        instance = res.unique().scalar_one()
        instance.status = InstanceStatus.BUSY
        instance.job = job_model
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
        job_model.job_provisioning_data = instance.job_provisioning_data
        job_model.used_instance_id = instance.id
        job_model.status = JobStatus.PROVISIONING
        job_model.last_processed_at = common_utils.get_current_datetime()
        await session.commit()
        return instance


async def _run_job_on_new_instance(
    project: ProjectModel,
    job_model: JobModel,
    run: Run,
    job: Job,
    project_ssh_public_key: str,
    project_ssh_private_key: str,
    master_job_provisioning_data: Optional[JobProvisioningData] = None,
    volumes: Optional[List[Volume]] = None,
    fleet_model: Optional[FleetModel] = None,
) -> Optional[Tuple[JobProvisioningData, InstanceOfferWithAvailability]]:
    if volumes is None:
        volumes = []
    fleet = None
    if fleet_model is not None:
        fleet = fleet_model_to_fleet(fleet_model)
    multinode = job.job_spec.jobs_per_replica > 1 or (
        fleet is not None and fleet.spec.configuration.placement == InstanceGroupPlacement.CLUSTER
    )
    offers = await get_offers_by_requirements(
        project=project,
        profile=run.run_spec.merged_profile,
        requirements=job.job_spec.requirements,
        exclude_not_available=True,
        multinode=multinode,
        master_job_provisioning_data=master_job_provisioning_data,
        volumes=volumes,
    )
    # Limit number of offers tried to prevent long-running processing
    # in case all offers fail.
    for backend, offer in offers[:15]:
        logger.debug(
            "%s: trying %s in %s/%s for $%0.4f per hour",
            fmt(job_model),
            offer.instance.name,
            offer.backend.value,
            offer.region,
            offer.price,
        )
        try:
            job_provisioning_data = await run_async(
                backend.compute().run_job,
                run,
                job,
                offer,
                project_ssh_public_key,
                project_ssh_private_key,
                volumes,
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


def _get_or_create_fleet_model_for_job(
    project: ProjectModel,
    run_model: RunModel,
    run: Run,
) -> FleetModel:
    if run_model.fleet is not None:
        return run_model.fleet
    placement = InstanceGroupPlacement.ANY
    if run.run_spec.configuration.type == "task" and run.run_spec.configuration.nodes > 1:
        placement = InstanceGroupPlacement.CLUSTER
    spec = FleetSpec(
        configuration=FleetConfiguration(
            name=run.run_spec.run_name,
            placement=placement,
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
    if len(fleet_model.instances) == 0:
        # No instances means the fleet is not in the db yet, so don't lock.
        return 0
    await wait_to_lock(PROCESSING_FLEETS_LOCK, PROCESSING_FLEETS_IDS, fleet_model.id)
    try:
        fleet_model = (
            (
                await session.execute(
                    select(FleetModel)
                    .where(FleetModel.id == fleet_model.id)
                    .options(joinedload(FleetModel.instances))
                    .execution_options(populate_existing=True)
                )
            )
            .unique()
            .scalar_one()
        )
        return len(fleet_model.instances)
    finally:
        PROCESSING_FLEETS_IDS.difference_update([fleet_model.id])


def _create_instance_model_for_job(
    project: ProjectModel,
    pool: PoolModel,
    fleet_model: FleetModel,
    run_spec: RunSpec,
    job_model: JobModel,
    job: Job,
    job_provisioning_data: JobProvisioningData,
    offer: InstanceOfferWithAvailability,
    instance_num: int,
) -> InstanceModel:
    profile = run_spec.merged_profile
    termination_policy = profile.termination_policy
    termination_idle_time = profile.termination_idle_time
    if not job_provisioning_data.dockerized:
        # terminate vastai/k8s instances immediately
        termination_policy = TerminationPolicy.DESTROY_AFTER_IDLE
        termination_idle_time = 0
    instance = InstanceModel(
        id=uuid.uuid4(),
        name=f"{fleet_model.name}-{instance_num}",
        instance_num=instance_num,
        project=project,
        pool=pool,
        created_at=common_utils.get_current_datetime(),
        started_at=common_utils.get_current_datetime(),
        status=InstanceStatus.PROVISIONING,
        unreachable=False,
        job_provisioning_data=job_provisioning_data.json(),
        offer=offer.json(),
        termination_policy=termination_policy,
        termination_idle_time=termination_idle_time,
        job=job_model,
        backend=offer.backend,
        price=offer.price,
        region=offer.region,
        volumes=[],
    )
    return instance


async def _attach_volumes(
    session: AsyncSession,
    project: ProjectModel,
    job_model: JobModel,
    instance: InstanceModel,
    volume_models: List[VolumeModel],
):
    job_provisioning_data = JobProvisioningData.__response__.parse_raw(
        instance.job_provisioning_data
    )
    backend = await get_project_backend_by_type_or_error(
        project=project,
        backend_type=job_provisioning_data.backend,
    )
    volumes_ids = sorted([v.id for v in volume_models])
    logger.info("Attaching volumes: %s", [v.name for v in volume_models])
    # Take lock to prevent attaching deleted volumes.
    # If the volume was deleted before the lock, fail the job.
    await wait_to_lock_many(PROCESSING_VOLUMES_LOCK, PROCESSING_VOLUMES_IDS, volumes_ids)
    try:
        for volume_model in volume_models:
            volume = volume_model_to_volume(volume_model)
            try:
                if volume.provisioning_data is not None and volume.provisioning_data.attachable:
                    await _attach_volume(
                        session=session,
                        backend=backend,
                        volume_model=volume_model,
                        instance=instance,
                        instance_id=job_provisioning_data.instance_id,
                    )
            except (ServerClientError, BackendError) as e:
                logger.warning("%s: failed to attached volume: %s", fmt(job_model), repr(e))
                job_model.status = JobStatus.TERMINATING
                # TODO: Replace with JobTerminationReason.VOLUME_ERROR in 0.19
                job_model.termination_reason = JobTerminationReason.TERMINATED_BY_SERVER
                job_model.termination_reason_message = "Failed to attach volume"
            except Exception:
                logger.exception(
                    "%s: got exception when attaching volume",
                    fmt(job_model),
                )
                job_model.status = JobStatus.TERMINATING
                # TODO: Replace with JobTerminationReason.VOLUME_ERROR in 0.19
                job_model.termination_reason = JobTerminationReason.TERMINATED_BY_SERVER
                job_model.termination_reason_message = "Failed to attach volume"
    finally:
        PROCESSING_VOLUMES_IDS.difference_update(volumes_ids)


async def _attach_volume(
    session: AsyncSession,
    backend: Backend,
    volume_model: VolumeModel,
    instance: InstanceModel,
    instance_id: str,
):
    await session.refresh(volume_model)
    if volume_model.deleted:
        raise ServerClientError("Cannot attach a deleted volume")
    volume = volume_model_to_volume(volume_model)
    attachment_data = await run_async(
        backend.compute().attach_volume,
        volume=volume,
        instance_id=instance_id,
    )
    volume_model.volume_attachment_data = attachment_data.json()
    instance.volumes.append(volume_model)
