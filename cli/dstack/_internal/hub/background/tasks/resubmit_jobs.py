from typing import List

from dstack._internal.backend.base import Backend
from dstack._internal.core.job import JobStatus
from dstack._internal.hub.db.models import Project
from dstack._internal.hub.repository.projects import ProjectManager
from dstack._internal.hub.routers.cache import get_backend
from dstack._internal.hub.services.backends import get_configurator
from dstack._internal.hub.utils.common import run_async
from dstack._internal.utils.common import get_milliseconds_since_epoch

RESUBMISSION_INTERVAL = 60


async def resubmit_jobs():
    projects = await ProjectManager.list()
    await _resubmit_projects_jobs(projects)


async def _resubmit_projects_jobs(projects: List[Project]):
    for project in projects:
        backend = await get_backend(project)
        configurator = get_configurator(backend)
        if configurator is None:
            continue
        await run_async(_resubmit_backend_jobs, backend)


def _resubmit_backend_jobs(backend: Backend):
    curr_time = get_milliseconds_since_epoch()
    for repo_head in backend.list_repo_heads():
        run_heads = backend.list_run_heads(
            repo_id=repo_head.repo_id,
            run_name=None,
            include_request_heads=True,
            interrupted_job_new_status=JobStatus.PENDING,
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
                    if (
                        job.retry_policy is not None
                        and job.retry_policy.retry
                        and curr_time - job.created_at < job.retry_policy.limit * 1000
                    ):
                        backend.resubmit_job(
                            job=job,
                            failed_to_start_job_new_status=JobStatus.PENDING,
                        )
                    else:
                        backend.resubmit_job(
                            job=job,
                            failed_to_start_job_new_status=JobStatus.FAILED,
                        )
