from typing import List

import google.api_core.exceptions

from dstack._internal.backend.base import Backend
from dstack._internal.core.error import NoMatchingInstanceError
from dstack._internal.core.job import Job, JobErrorCode, JobStatus
from dstack._internal.hub.db.models import Project
from dstack._internal.hub.repository.jobs import JobManager
from dstack._internal.hub.repository.projects import ProjectManager
from dstack._internal.hub.services.backends.cache import get_project_backends
from dstack._internal.hub.services.common import (
    get_backends,
    get_instance_candidates,
    not_available,
)
from dstack._internal.hub.utils.common import run_async
from dstack._internal.utils.common import get_milliseconds_since_epoch
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

RESUBMISSION_INTERVAL = 60


async def resubmit_jobs():
    projects = await ProjectManager.list()
    await _resubmit_projects_jobs(projects)


async def _resubmit_projects_jobs(projects: List[Project]):
    for project in projects:
        logger.debug("Resubmitting jobs for %s project", project.name)
        logger.debug("Resubmitting not started jobs")
        await _resubmit_not_started_jobs(project)
        logger.debug("Finished resubmitting not started jobs for %s project", project.name)
        backends = await get_project_backends(project)
        for db_backend, backend in backends:
            logger.debug("Resubmitting interrupted jobs for %s backend", db_backend.name)
            try:
                await run_async(_resubmit_interrupted_jobs, project, backend)
            except google.api_core.exceptions.RetryError as e:
                logger.warning(
                    "Error when resubmitting jobs for %s backend: %s", db_backend.name, e.message
                )
            logger.debug("Finished resubmitting interrupted jobs for %s backend", db_backend.name)
        logger.debug("Finished resubmitting jobs for %s project", project.name)


async def _resubmit_not_started_jobs(project: Project):
    jobs = await JobManager.list_jobs(
        project_name=project.name,
        status=JobStatus.PENDING,
    )
    for job in jobs:
        _update_job_submission(job)
        if not job.retry_active():
            job.status = JobStatus.FAILED
            job.error_code = JobErrorCode.FAILED_TO_START_DUE_TO_NO_CAPACITY
            await JobManager.update(project_name=project.name, job=job)
            continue
        backends = await get_backends(project, selected_backends=job.backends)
        backends = [b for _, b in backends]
        candidates = await get_instance_candidates(backends, job, exclude_not_available=True)
        for backend, offer in candidates:
            logger.info(
                "Trying %s in %s/%s for $%0.4f per hour",
                offer.instance.instance_name,
                backend.name,
                offer.region,
                offer.price,
            )
            try:
                await run_async(
                    backend.run_job,
                    job,
                    project.ssh_private_key,
                    offer,
                )
            except NoMatchingInstanceError:
                continue
            else:
                logger.info("Resubmitted not started job %s", job.job_id)
                await JobManager.delete_job(project_name=project.name, job_id=job.job_id)
                break
        job.status = JobStatus.PENDING
        await JobManager.update(project_name=project.name, job=job)


def _resubmit_interrupted_jobs(project: Project, backend: Backend):
    curr_time = get_milliseconds_since_epoch()
    for repo_head in backend.list_repo_heads():
        run_heads = backend.list_run_heads(
            repo_id=repo_head.repo_id,
            run_name=None,
            include_request_heads=True,
        )
        for run_head in run_heads:
            job_heads = backend.list_job_heads(
                repo_id=repo_head.repo_id, run_name=run_head.run_name
            )
            for job_head in job_heads:
                if (
                    job_head.status == JobStatus.PENDING
                    and curr_time - job_head.submitted_at > RESUBMISSION_INTERVAL * 1000
                ):
                    job = backend.get_job(repo_id=repo_head.repo_id, job_id=job_head.job_id)
                    if not job.retry_active():
                        job.status = JobStatus.FAILED
                        backend.update_job(job)
                        continue
                    _update_job_submission(job)
                    offers = backend.get_instance_candidates(
                        requirements=job.requirements, spot_policy=job.spot_policy
                    )
                    offers = [offer for offer in offers if offer.availability not in not_available]
                    offers = sorted(offers, key=lambda x: x.price)
                    for offer in offers:
                        logger.debug(
                            "Trying %s in %s/%s for $%0.4f per hour",
                            offer.instance.instance_name,
                            backend.name,
                            offer.region,
                            offer.price,
                        )
                        try:
                            backend.run_job(
                                job=job,
                                project_private_key=project.ssh_private_key,
                                offer=offer,
                            )
                            logger.info("Resubmitted job %s", job.job_id)
                            break
                        except NoMatchingInstanceError:
                            continue
                    else:
                        job.status = JobStatus.PENDING
                        backend.update_job(job)


def _update_job_submission(job: Job):
    job.status = JobStatus.SUBMITTED
    job.submission_num += 1
    job.submitted_at = get_milliseconds_since_epoch()
