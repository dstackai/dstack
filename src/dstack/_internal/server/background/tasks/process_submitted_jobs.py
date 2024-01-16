from typing import List, Optional, Tuple
from uuid import UUID

from pydantic import parse_raw_as
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.backends.base import Backend
from dstack._internal.core.errors import BackendError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceOfferWithAvailability,
    LaunchedInstanceInfo,
)
from dstack._internal.core.models.profiles import (
    DEFAULT_POOL_NAME,
    CreationPolicy,
    Profile,
    TerminationPolicy,
)
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
from dstack._internal.server.models import InstanceModel, JobModel, PoolModel, RunModel
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services.jobs import (
    SUBMITTED_PROCESSING_JOBS_IDS,
    SUBMITTED_PROCESSING_JOBS_LOCK,
)
from dstack._internal.server.services.logging import job_log
from dstack._internal.server.services.pools import (
    get_pool_instances,
    instance_model_to_instance,
    show_pool,
)
from dstack._internal.server.services.runs import run_model_to_run
from dstack._internal.server.settings import LOCAL_BACKEND_ENABLED
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


def check_relevance(profile: Profile, instance_model: InstanceModel) -> bool:

    jpd: JobProvisioningData = parse_raw_as(
        JobProvisioningData, instance_model.job_provisioning_data
    )

    if LOCAL_BACKEND_ENABLED and jpd.backend == BackendType.LOCAL:
        return True

    instance = instance_model_to_instance(instance_model)

    if profile.backends is not None and instance.backend not in profile.backends:
        return False

    instance_resources = jpd.instance_type.resources

    if profile.resources.cpu is not None and profile.resources.cpu < instance_resources.cpus:
        return False

    # TODO: full check
    if isinstance(profile.resources.gpu, int):
        if profile.resources.gpu < len(instance_resources.gpus):
            return False

    return True
    # TODO: memory, shm_size, disk


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

    # check default pool
    pool = project_model.default_pool
    if pool is None:
        pool = PoolModel(
            name=DEFAULT_POOL_NAME,
            project=project_model,
        )
        session.add(pool)
        await session.commit()
        if pool.id is not None:
            project_model.default_pool_id = pool.id

    profile = parse_raw_as(RunSpec, run_model.run_spec).profile
    run_pool = profile.pool_name
    if run_pool is None:
        run_pool = pool.name

    # pool capacity
    pool_instances = await get_pool_instances(session, project_model, run_pool)
    available_instanses = (p for p in pool_instances if p.status == InstanceStatus.READY)
    relevant_instances: List[InstanceModel] = []
    for instance in available_instanses:
        if check_relevance(profile, instance):
            relevant_instances.append(instance)

    if relevant_instances:

        sorted_instances = sorted(relevant_instances, key=lambda instance: instance.name)
        instance = sorted_instances[0]

        instance.status = InstanceStatus.BUSY

        logger.info(*job_log("now is provisioning", job_model))
        job_model.job_provisioning_data = instance.job_provisioning_data
        job_model.status = JobStatus.PROVISIONING
        job_model.last_processed_at = common_utils.get_current_datetime()

        await session.commit()

        return

    if profile.creation_policy == CreationPolicy.REUSE:
        job_model.status = JobStatus.FAILED
        job_model.error_code = JobErrorCode.FAILED_TO_START_DUE_TO_NO_CAPACITY
        job_model.last_processed_at = common_utils.get_current_datetime()
        await session.commit()
        return

    # create a new cloud instance
    run = run_model_to_run(run_model)
    job = run.jobs[job_model.job_num]
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
        job_provisioning_data.pool_id = str(pool.id)
        job_model.job_provisioning_data = job_provisioning_data.json()
        job_model.status = JobStatus.PROVISIONING

        im = InstanceModel(
            name=job.job_spec.job_name,
            project=project_model,
            pool=pool,
            status=InstanceStatus.CREATING,
            job_provisioning_data=job_provisioning_data.json(),
            offer=offer.json(),
            termination_policy=profile.termination_policy,
            termination_idle_time=profile.termination_idle_time,
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
    try:
        requirements = job.job_spec.requirements
        offers = await backends_services.get_instance_offers(
            backends, requirements, exclude_not_available=True
        )
    except BackendError as e:
        logger.warning(*job_log("failed to get instance offers: %s", job_model, repr(e)))
        return (None, None)
    for backend, offer in offers:
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
