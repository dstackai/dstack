import asyncio
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.backends.base import Backend
from dstack._internal.core.errors import BackendError
from dstack._internal.core.models.instances import LaunchedInstanceInfo
from dstack._internal.core.models.runs import (
    Job,
    JobErrorCode,
    JobProvisioningData,
    JobStatus,
    Run,
)
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import JobModel, RunModel
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services.runs import run_model_to_run
from dstack._internal.server.utils.common import run_async
from dstack._internal.utils import common as common_utils
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


_PROCESSING_JOBS_LOCK = asyncio.Lock()
_PROCESSING_JOBS_IDS = set()


async def process_submitted_jobs():
    async with get_session_ctx() as session:
        async with _PROCESSING_JOBS_LOCK:
            res = await session.execute(
                select(JobModel)
                .where(
                    JobModel.status == JobStatus.SUBMITTED,
                    JobModel.id.not_in(_PROCESSING_JOBS_IDS),
                )
                .limit(1)  # TODO process multiple at once
            )
            job_model = res.scalar()
            if job_model is None:
                return

            _PROCESSING_JOBS_IDS.add(job_model.id)

    try:
        await _process_job(job_id=job_model.id)
    finally:
        async with _PROCESSING_JOBS_LOCK:
            _PROCESSING_JOBS_IDS.remove(job_model.id)


async def _process_job(job_id: UUID):
    async with get_session_ctx() as session:
        res = await session.execute(
            select(JobModel)
            .where(JobModel.id == job_id)
            .options(joinedload(JobModel.run).joinedload(RunModel.project))
            .options(joinedload(JobModel.run).joinedload(RunModel.user))
        )
        job_model = res.scalar_one()
        await _process_submitted_job(
            session=session,
            job_model=job_model,
        )


async def _process_submitted_job(session: AsyncSession, job_model: JobModel):
    logger.debug("Provisioning job %s", job_model.job_name)
    run_model = job_model.run
    run = run_model_to_run(run_model, include_job_submissions=False)
    job = run.jobs[job_model.job_num]
    backends = await backends_services.get_project_backends(project=run_model.project)
    job_provisioning_data = await _run_job(run=run, job=job, backends=backends)
    if job_provisioning_data is not None:
        logger.debug("Provisioning job %s succeded", job_model.job_name)
        job_model.job_provisioning_data = job_provisioning_data.json()
        job_model.status = JobStatus.PROVISIONING
    else:
        # TODO resubmit
        logger.debug("Provisioning job %s failed", job_model.job_name)
        job_model.status = JobStatus.FAILED
        job_model.error_code = JobErrorCode.FAILED_TO_START_DUE_TO_NO_CAPACITY
    job_model.last_processed_at = common_utils.get_current_datetime()
    await session.commit()


async def _run_job(run: Run, job: Job, backends: List[Backend]) -> Optional[JobProvisioningData]:
    candidates = await backends_services.get_instance_candidates(
        backends, job, exclude_not_available=True
    )
    for backend, offer in candidates:
        logger.info(
            "Trying %s in %s/%s for $%0.4f per hour",
            offer.instance.name,
            backend.TYPE,
            offer.region,
            offer.price,
        )
        try:
            launched_instance_info: LaunchedInstanceInfo = await run_async(
                backend.compute().run_job,
                run,
                job,
                offer,
            )
        except BackendError as e:
            logger.debug("Instance launch failed: %s", e)
            continue
        else:
            return JobProvisioningData(
                hostname=launched_instance_info.ip_address,
                instance_type=offer.instance,
                instance_id=launched_instance_info.instance_id,
                region=launched_instance_info.region,
                price=offer.price,
            )
    return None
