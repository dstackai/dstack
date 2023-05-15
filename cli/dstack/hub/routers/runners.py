from fastapi import APIRouter, Depends, HTTPException, status

from dstack.core.error import NoMatchingInstanceError
from dstack.core.job import Job, JobStatus
from dstack.hub.models import StopRunners
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import error_detail, get_project
from dstack.hub.security.permissions import ProjectMember

router = APIRouter(
    prefix="/api/project", tags=["runners"], dependencies=[Depends(ProjectMember())]
)


@router.post("/{project_name}/runners/run")
async def run_runners(project_name: str, job: Job):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    try:
        backend.run_job(job=job, failed_to_start_job_new_status=JobStatus.PENDING)
    except NoMatchingInstanceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(e.message, code=NoMatchingInstanceError.code),
        )


@router.post("/{project_name}/runners/stop")
async def stop_runners(project_name: str, body: StopRunners):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    backend.stop_job(body.repo_id, abort=body.abort, job_id=body.job_id)
