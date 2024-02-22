from typing import List, Optional, Tuple
from uuid import UUID

from pydantic import parse_raw_as
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.backends.base import Backend
from dstack._internal.core.errors import BackendError
from dstack._internal.core.models.instances import (
    InstanceOfferWithAvailability,
    LaunchedInstanceInfo,
)
from dstack._internal.core.models.profiles import CreationPolicy, TerminationPolicy
from dstack._internal.core.models.runs import (
    InstanceStatus,
    Job,
    JobErrorCode,
    JobProvisioningData,
    JobStatus,
    Run,
    RunSpec,
)
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import InstanceModel, JobModel, RunModel
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services.jobs import (
    PROCESSING_POOL_LOCK,
    SUBMITTED_PROCESSING_JOBS_IDS,
    SUBMITTED_PROCESSING_JOBS_LOCK,
)
from dstack._internal.server.services.logging import job_log
from dstack._internal.server.services.pools import (
    filter_pool_instances,
    get_or_create_default_pool_by_name,
    get_pool_instances,
)
from dstack._internal.server.services.runs import run_model_to_run
from dstack._internal.server.utils.common import run_async
from dstack._internal.utils import common as common_utils
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def process_submitted_jobs():
    async with get_session_ctx() as session:
        async with SUBMITTED_PROCESSING_JOBS_LOCK:
            res = await session.execute(
                select(JobModel)
                .where(
                    JobModel.status == JobStatus.SUBMITTED,
                    JobModel.id.not_in(SUBMITTED_PROCESSING_JOBS_IDS),
                )
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
    logger.debug(*job_log("provisioning", job_model))
    res = await session.execute(
        select(RunModel)
        .where(RunModel.id == job_model.run_id)
        .options(joinedload(RunModel.project))
        .options(joinedload(RunModel.user))
    )
    run_model = res.scalar_one()
    project_model = run_model.project

    run_spec = parse_raw_as(RunSpec, run_model.run_spec)
    profile = run_spec.profile

    # check default pool
    pool = project_model.default_pool
    if pool is None:
        pool = await get_or_create_default_pool_by_name(
            session, project_model, pool_name=profile.pool_name
        )
        project_model.default_pool = pool

    async with PROCESSING_POOL_LOCK:
        # pool capacity
        pool_instances = await get_pool_instances(session, project_model, pool.name)
        relevant_instances = filter_pool_instances(
            pool_instances, profile, run_spec.configuration.resources, status=InstanceStatus.READY
        )

        if relevant_instances:
            sorted_instances = sorted(relevant_instances, key=lambda instance: instance.name)
            instance = sorted_instances[0]
            instance.status = InstanceStatus.BUSY
            instance.job = job_model

            logger.info(*job_log("now is provisioning", job_model))
            job_model.job_provisioning_data = instance.job_provisioning_data
            job_model.status = JobStatus.PROVISIONING
            job_model.last_processed_at = common_utils.get_current_datetime()

            await session.commit()

            return

    run = run_model_to_run(run_model)
    job = run.jobs[job_model.job_num]

    if profile.creation_policy == CreationPolicy.REUSE:
        logger.debug(*job_log("reuse instance failed", job_model))
        if job.is_retry_active():
            logger.debug(*job_log("now is pending because retry is active", job_model))
            job_model.status = JobStatus.PENDING
        else:
            job_model.status = JobStatus.FAILED
            job_model.error_code = JobErrorCode.FAILED_TO_START_DUE_TO_NO_CAPACITY
        job_model.last_processed_at = common_utils.get_current_datetime()
        await session.commit()
        return

    # create a new cloud instance
    backends = await backends_services.get_project_backends(project=run_model.project)

    # TODO: create VM (backend.compute().create_instance)
    job_provisioning_data, offer = await _run_job(
        job_model=job_model,
        run=run,
        job=job,
        backends=backends,
        project_ssh_public_key=project_model.ssh_public_key,
        project_ssh_private_key=project_model.ssh_private_key,
    )
    if job_provisioning_data is not None and offer is not None:
        logger.info(*job_log("now is provisioning", job_model))

        job_model.job_provisioning_data = job_provisioning_data.json()
        job_model.status = JobStatus.PROVISIONING

        termination_policy = profile.termination_policy
        termination_idle_time = profile.termination_idle_time
        if not job_provisioning_data.dockerized:
            # terminate vastai/k8s instances immediately
            termination_policy = TerminationPolicy.DESTROY_AFTER_IDLE
            termination_idle_time = 0

        im = InstanceModel(
            name=job.job_spec.job_name,  # TODO: make new name
            project=project_model,
            pool=pool,
            created_at=common_utils.get_current_datetime(),
            started_at=common_utils.get_current_datetime(),
            status=InstanceStatus.STARTING,
            job_provisioning_data=job_provisioning_data.json(),
            offer=offer.json(),
            termination_policy=termination_policy,
            termination_idle_time=termination_idle_time,
            job=job_model,
            backend=offer.backend,
            price=offer.price,
            region=offer.region,
        )
        session.add(im)

    else:
        logger.debug(*job_log("provisioning failed", job_model))
        if job.is_retry_active():
            logger.debug(*job_log("now is pending because retry is active", job_model))
            job_model.status = JobStatus.PENDING
        else:
            job_model.status = JobStatus.FAILED
            job_model.error_code = JobErrorCode.FAILED_TO_START_DUE_TO_NO_CAPACITY
    job_model.last_processed_at = common_utils.get_current_datetime()
    await session.commit()


async def _run_job(
    job_model: JobModel,
    run: Run,
    job: Job,
    backends: List[Backend],
    project_ssh_public_key: str,
    project_ssh_private_key: str,
) -> Tuple[Optional[JobProvisioningData], Optional[InstanceOfferWithAvailability]]:
    if run.run_spec.profile.backends is not None:
        backends = [b for b in backends if b.TYPE in run.run_spec.profile.backends]

    requirements = job.job_spec.requirements
    offers = await backends_services.get_instance_offers(
        backends, requirements, exclude_not_available=True
    )
    # Limit number of offers tried to prevent long-running processing
    # in case all offers fail.
    for backend, offer in offers[:15]:
        logger.debug(
            *job_log(
                "trying %s in %s/%s for $%0.4f per hour",
                job_model,
                offer.instance.name,
                offer.backend.value,
                offer.region,
                offer.price,
            )
        )
        try:
            launched_instance_info: LaunchedInstanceInfo = await run_async(
                backend.compute().run_job,
                run,
                job,
                offer,
                project_ssh_public_key,
                project_ssh_private_key,
            )
        except BackendError as e:
            logger.warning(
                *job_log(
                    "%s launch in %s/%s failed: %s",
                    job_model,
                    offer.instance.name,
                    offer.backend.value,
                    offer.region,
                    repr(e),
                )
            )
            continue
        except Exception:
            logger.exception(
                *job_log(
                    "got exception when launching %s in %s/%s",
                    job_model,
                    offer.instance.name,
                    offer.backend.value,
                    offer.region,
                )
            )
            continue
        else:
            job_provisioning_data = JobProvisioningData(
                backend=backend.TYPE,
                instance_type=offer.instance,
                instance_id=launched_instance_info.instance_id,
                hostname=launched_instance_info.ip_address,
                region=launched_instance_info.region,
                price=offer.price,
                username=launched_instance_info.username,
                ssh_port=launched_instance_info.ssh_port,
                dockerized=launched_instance_info.dockerized,
                ssh_proxy=launched_instance_info.ssh_proxy,
                backend_data=launched_instance_info.backend_data,
            )

            return (job_provisioning_data, offer)
    return (None, None)
