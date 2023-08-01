from fastapi import APIRouter, Depends, HTTPException, status

from dstack._internal.core.build import BuildNotFoundError
from dstack._internal.core.error import NoMatchingInstanceError, SSHCommandError
from dstack._internal.core.job import Job, JobStatus
from dstack._internal.hub.models import StopRunners
from dstack._internal.hub.routers.util import call_backend, error_detail, get_backend, get_project
from dstack._internal.hub.security.permissions import ProjectMember

router = APIRouter(
    prefix="/api/project", tags=["runners"], dependencies=[Depends(ProjectMember())]
)


@router.post("/{project_name}/runners/run")
async def run(project_name: str, job: Job):
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    failed_to_start_job_new_status = JobStatus.FAILED
    if job.retry_policy.retry:
        failed_to_start_job_new_status = JobStatus.PENDING
    try:
        await call_backend(backend.run_job, job, failed_to_start_job_new_status)
    except NoMatchingInstanceError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                "No instance type matching requirements", code=NoMatchingInstanceError.code
            ),
        )
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


@router.post("/{project_name}/runners/restart")
async def restart(project_name: str, job: Job):
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    await call_backend(backend.restart_job, job)


@router.post("/{project_name}/runners/stop")
async def stop(project_name: str, body: StopRunners):
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    await call_backend(backend.stop_job, body.repo_id, body.job_id, body.terminate, body.abort)
