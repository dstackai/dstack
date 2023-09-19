import asyncio
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.utils.common
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
from dstack._internal.server.db import get_session_ctx, session_decorator
from dstack._internal.server.models import JobModel
from dstack._internal.server.services.backends import get_instance_candidates, get_project_backends
from dstack._internal.server.services.runs import run_model_to_run
from dstack._internal.server.utils.common import run_async
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
        await _process_job(session=session, job_model=job_model)
    finally:
        async with _PROCESSING_JOBS_LOCK:
            _PROCESSING_JOBS_IDS.remove(job_model.id)


async def _process_job(job_model: JobModel):
    async with get_session_ctx() as session:
        _process_submitted_job(
            session=session,
            job_model=job_model,
        )


async def _process_submitted_job(session: AsyncSession, job_model: JobModel):
    run_model = job_model.run
    run = run_model_to_run(run_model)
    job = run.jobs[job_model.job_num]
    backends = get_project_backends(project=run_model.project)
    backends = [backend for _, backend in backends]
    job_provisioning_data = await _run_job(run=run, job=job, backends=backends)
    if job_provisioning_data is not None:
        job_model.job_provisioning_data = job_provisioning_data.json()
        job_model.status = JobStatus.PROVISIONING
    else:
        # TODO resubmit
        job_model.status = JobStatus.FAILED
        job_model.error_code = JobErrorCode.FAILED_TO_START_DUE_TO_NO_CAPACITY
    job_model.last_processed_at = dstack._internal.utils.common.get_current_datetime()
    await session.commit()


async def _run_job(run: Run, job: Job, backends: List[Backend]) -> Optional[JobProvisioningData]:
    candidates = await get_instance_candidates(backends, job, exclude_not_available=True)
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
        except BackendError:
            continue
        else:
            return JobProvisioningData(
                hostname=launched_instance_info,
                instance_type=offer.instance,
                instance_id=launched_instance_info.instance_id,
                spot_request_id=launched_instance_info.spot_request_id,
                region=launched_instance_info.region,
                price=offer.price,
            )
    return None
