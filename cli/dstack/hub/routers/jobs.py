from typing import List, Optional

from fastapi import APIRouter, Depends

from dstack.core.job import Job, JobHead
from dstack.core.repo import RepoRef
from dstack.hub.models import JobsGet, JobsList
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import get_project
from dstack.hub.security.permissions import ProjectMember

router = APIRouter(prefix="/api/project", tags=["jobs"], dependencies=[Depends(ProjectMember())])


@router.post("/{project_name}/jobs/create")
async def create_job(project_name: str, job: Job):
    project = await get_project(project_name=project_name)
    backend = get_backend(project, job.repo)
    backend.create_job(job=job)


@router.post("/{project_name}/jobs/get")
async def get_job(project_name: str, body: JobsGet) -> Job:
    project = await get_project(project_name=project_name)
    backend = get_backend(project, body.repo)
    return backend.get_job(job_id=body.job_id)


@router.post("/{project_name}/jobs/list")
async def list_job(project_name: str, body: JobsList) -> List[Job]:
    project = await get_project(project_name=project_name)
    backend = get_backend(project, body.repo)
    return backend.list_jobs(run_name=body.run_name)


@router.post("/{project_name}/jobs/list/heads")
async def list_heads_job(
    project_name: str, repo: RepoRef, run_name: Optional[str] = None
) -> List[JobHead]:
    project = await get_project(project_name=project_name)
    backend = get_backend(project, repo)
    return backend.list_job_heads(run_name=run_name)


@router.post("/{project_name}/jobs/delete")
async def delete_job(project_name: str, body: JobsGet):
    project = await get_project(project_name=project_name)
    backend = get_backend(project, body.repo)
    backend.delete_job_head(job_id=body.job_id)
