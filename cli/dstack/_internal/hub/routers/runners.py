from fastapi import APIRouter, Depends, HTTPException, status

from dstack._internal.core.error import NoMatchingInstanceError
from dstack._internal.core.job import Job, JobStatus
from dstack._internal.hub.models import StopRunners
from dstack._internal.hub.routers.cache import get_backend
from dstack._internal.hub.routers.util import error_detail, get_project
from dstack._internal.hub.security.permissions import ProjectMember
from dstack._internal.hub.utils.common import run_async

router = APIRouter(
    prefix="/api/project", tags=["runners"], dependencies=[Depends(ProjectMember())]
)


@router.post("/{project_name}/runners/run")
async def run_runners(project_name: str, job: Job):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    try:
        await run_async(backend.run_job, job, JobStatus.PENDING)
    except NoMatchingInstanceError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                NoMatchingInstanceError.message, code=NoMatchingInstanceError.code
            ),
        )


@router.post("/{project_name}/runners/stop")
async def stop_runners(project_name: str, body: StopRunners):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    await run_async(backend.stop_job, body.repo_id, body.abort, body.job_id)
