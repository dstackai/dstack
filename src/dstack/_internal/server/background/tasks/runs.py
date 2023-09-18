import asyncio
from typing import List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.backends.base import Backend
from dstack._internal.core.errors import BackendError
from dstack._internal.core.models.instances import LaunchedInstanceInfo
from dstack._internal.core.models.runs import Job, JobProvisioningData, JobStatus, Run
from dstack._internal.server.db import session_decorator
from dstack._internal.server.models import JobModel
from dstack._internal.server.services.backends import get_instance_candidates, get_project_backends
from dstack._internal.server.services.runs import run_model_to_run
from dstack._internal.server.utils.common import run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


_PROVISIONING_JOBS_LOCK = asyncio.Lock()
_PROVISIONING_JOBS_IDS = set()


@session_decorator
async def handle_submitted_jobs(session: AsyncSession):
    async with _PROVISIONING_JOBS_LOCK:
        res = await session.execute(
            select(JobModel)
            .where(
                JobModel.status == JobStatus.SUBMITTED, JobModel.id.not_in(_PROVISIONING_JOBS_IDS)
            )
            .limit(1)
        )
        job_model = res.scalar()
        if job_model is None:
            return

        _PROVISIONING_JOBS_IDS.add(job_model.id)

    await _handle_submitted_job(session=session, job_model=job_model)


async def _handle_submitted_job(session: AsyncSession, job_model: JobModel):
    run_model = job_model.run
    run = run_model_to_run(run_model)
    job = run.jobs[job_model.job_num]
    backends = get_project_backends(project=run_model.project)
    backends = [backend for _, backend in backends]
    job_provisioning_data = await _run_job(run=run, job=job, backends=backends)
    job_model.job_provisioning_data = job_provisioning_data.json()
    job_model.status = JobStatus.PROVISIONING
    await session.commit()


async def _run_job(run: Run, job: Job, backends: List[Backend]) -> JobProvisioningData:
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
                error_code=None,
                container_exit_code=None,
                hostname=launched_instance_info,
                instance_type=offer.instance,
                instance_id=launched_instance_info.instance_id,
                spot_request_id=launched_instance_info.spot_request_id,
                region=launched_instance_info.region,
                price=offer.price,
            )
