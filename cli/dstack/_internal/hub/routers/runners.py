from fastapi import APIRouter, Depends, HTTPException, status

from dstack._internal.core.build import BuildNotFoundError
from dstack._internal.core.error import NoMatchingInstanceError, SSHCommandError
from dstack._internal.core.job import Job, JobErrorCode, JobStatus
from dstack._internal.hub.routers.util import (
    call_backend,
    error_detail,
    get_backends,
    get_job_backend,
    get_project,
    get_run_backend,
)
from dstack._internal.hub.schemas import StopRunners
from dstack._internal.hub.security.permissions import ProjectMember

router = APIRouter(
    prefix="/api/project", tags=["runners"], dependencies=[Depends(ProjectMember())]
)


@router.post("/{project_name}/runners/run")
async def run(project_name: str, job: Job):
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)
    failed_to_start_job_new_status = JobStatus.FAILED
    if job.retry_policy.retry:
        failed_to_start_job_new_status = JobStatus.PENDING
    for _, backend in backends:
        try:
            await call_backend(backend.run_job, job, failed_to_start_job_new_status)
            return
        except NoMatchingInstanceError:
            continue
        except BuildNotFoundError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail(msg=e.message, code=e.code),
            )
        except SSHCommandError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail(msg=e.message, code=e.code),
            )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=error_detail("Run failed due to no capacity", code=NoMatchingInstanceError.code),
    )


@router.post("/{project_name}/runners/restart")
async def restart(project_name: str, job: Job):
    project = await get_project(project_name=project_name)
    _, backend = await get_run_backend(project, job.repo.repo_id, job.run_name)
    await call_backend(backend.restart_job, job)


@router.post("/{project_name}/runners/stop")
async def stop(project_name: str, body: StopRunners):
    project = await get_project(project_name=project_name)
    _, backend = await get_job_backend(project, body.repo_id, body.job_id)
    await call_backend(backend.stop_job, body.repo_id, body.job_id, body.terminate, body.abort)
