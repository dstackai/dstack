from fastapi import APIRouter, Depends

from dstack.core.job import Job, JobStatus
from dstack.hub.models import StopRunners
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import get_project
from dstack.hub.security.permissions import ProjectMember

router = APIRouter(
    prefix="/api/project", tags=["runners"], dependencies=[Depends(ProjectMember())]
)


@router.post("/{project_name}/runners/run")
async def run_runners(project_name: str, job: Job):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    backend.run_job(job=job, failed_to_start_job_new_status=JobStatus.PENDING)


@router.post("/{project_name}/runners/stop")
async def stop_runners(project_name: str, body: StopRunners):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    backend.stop_job(repo_address=body.repo_address, job_id=body.job_id, abort=body.abort)
