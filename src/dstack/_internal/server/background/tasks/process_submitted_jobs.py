import uuid
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.errors import BackendError
from dstack._internal.core.models.instances import (
    InstanceOfferWithAvailability,
)
from dstack._internal.core.models.profiles import (
    CreationPolicy,
    TerminationPolicy,
)
from dstack._internal.core.models.runs import (
    InstanceStatus,
    Job,
    JobProvisioningData,
    JobStatus,
    JobTerminationReason,
    Requirements,
    Run,
    RunSpec,
)
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import (
    InstanceModel,
    JobModel,
    PoolModel,
    ProjectModel,
    RunModel,
)
from dstack._internal.server.services.jobs import (
    PROCESSING_POOL_LOCK,
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
    get_offers_by_requirements,
    run_model_to_run,
)
from dstack._internal.server.utils.common import run_async
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
        await _process_job(job_id=job_model.id)
    finally:
        SUBMITTED_PROCESSING_JOBS_IDS.remove(job_model.id)


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
        .options(joinedload(RunModel.project))
        .options(joinedload(RunModel.user))
    )
    run_model = res.scalar_one()
    project_model = run_model.project
    run_spec = RunSpec.__response__.parse_raw(run_model.run_spec)
    profile = run_spec.merged_profile

    run = run_model_to_run(run_model)
    job = find_job(run.jobs, job_model.replica_num, job_model.job_num)

    master_job = find_job(run.jobs, job_model.replica_num, 0)
    master_job_provisioning_data = None
    # Wait until the master job is provisioned to provision in the same cluster
    if job.job_spec.job_num != 0:
        if master_job.job_submissions[-1].job_provisioning_data is None:
            job_model.last_processed_at = common_utils.get_current_datetime()
            await session.commit()
            return
        master_job_provisioning_data = JobProvisioningData.__response__.parse_obj(
            master_job.job_submissions[-1].job_provisioning_data
        )

    # Try to provision on an instance from the pool
    pool = await get_or_create_pool_by_name(
        session=session,
        project=project_model,
        pool_name=profile.pool_name,
    )
    instance = await _run_job_on_pool_instance(
        session=session,
        pool=pool,
        run_spec=run_spec,
        job_model=job_model,
        job=job,
        master_job_provisioning_data=master_job_provisioning_data,
    )
    if instance is not None:
        return

    if profile.creation_policy == CreationPolicy.REUSE:
        logger.debug("%s: reuse instance failed", fmt(job_model))
        job_model.status = JobStatus.TERMINATING
        job_model.termination_reason = JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY
        job_model.last_processed_at = common_utils.get_current_datetime()
        await session.commit()
        return

    # Create a new cloud instance
    run_job_result = await _run_job_on_new_instance(
        project_model=project_model,
        job_model=job_model,
        run=run,
        job=job,
        project_ssh_public_key=project_model.ssh_public_key,
        project_ssh_private_key=project_model.ssh_private_key,
        master_job_provisioning_data=master_job_provisioning_data,
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
    instance = _create_instance_model_for_job(
        project_model=project_model,
        pool=pool,
        run_spec=run_spec,
        job_model=job_model,
        job=job,
        job_provisioning_data=job_provisioning_data,
        offer=offer,
    )
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
    await session.flush()  # to get im.id
    job_model.used_instance_id = instance.id
    job_model.last_processed_at = common_utils.get_current_datetime()
    await session.commit()


async def _run_job_on_pool_instance(
    session: AsyncSession,
    pool: PoolModel,
    run_spec: RunSpec,
    job_model: JobModel,
    job: Job,
    master_job_provisioning_data: Optional[JobProvisioningData] = None,
) -> Optional[InstanceModel]:
    profile = run_spec.merged_profile
    async with PROCESSING_POOL_LOCK:
        pool_instances = get_pool_instances(pool)
        requirements = Requirements(
            resources=run_spec.configuration.resources,
            max_price=profile.max_price,
            spot=job.job_spec.requirements.spot,
        )
        relevant_instances = filter_pool_instances(
            pool_instances=pool_instances,
            profile=profile,
            requirements=requirements,
            status=InstanceStatus.IDLE,
            multinode=job.job_spec.jobs_per_replica > 1,
            master_job_provisioning_data=master_job_provisioning_data,
        )
        if len(relevant_instances) == 0:
            return None
        sorted_instances = sorted(relevant_instances, key=lambda instance: instance.name)
        instance = sorted_instances[0]
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
    project_model: ProjectModel,
    job_model: JobModel,
    run: Run,
    job: Job,
    project_ssh_public_key: str,
    project_ssh_private_key: str,
    master_job_provisioning_data: Optional[JobProvisioningData] = None,
) -> Optional[Tuple[JobProvisioningData, InstanceOfferWithAvailability]]:
    offers = await get_offers_by_requirements(
        project=project_model,
        profile=run.run_spec.merged_profile,
        requirements=job.job_spec.requirements,
        exclude_not_available=True,
        multinode=job.job_spec.jobs_per_replica > 1,
        master_job_provisioning_data=master_job_provisioning_data,
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


def _create_instance_model_for_job(
    project_model: ProjectModel,
    pool: PoolModel,
    run_spec: RunSpec,
    job_model: JobModel,
    job: Job,
    job_provisioning_data: JobProvisioningData,
    offer: InstanceOfferWithAvailability,
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
        name=job.job_spec.job_name,  # TODO: make new name
        project=project_model,
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
    )
    return instance
