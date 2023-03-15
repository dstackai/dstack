from typing import List, Optional

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

from dstack.core.job import Job, JobHead
from dstack.core.repo import RepoAddress
from dstack.hub.models import JobsGet, JobsList
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import get_project
from dstack.hub.security.scope import Scope

router = APIRouter(prefix="/api/project", tags=["jobs"])

security = HTTPBearer()


@router.post("/{project_name}/jobs/create", dependencies=[Depends(Scope("jobs:create:write"))])
async def create_job(project_name: str, job: Job):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    backend.create_job(job=job)


@router.get(
    "/{project_name}/jobs/get", dependencies=[Depends(Scope("jobs:get:read"))], response_model=Job
)
async def get_job(project_name: str, body: JobsGet):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    return backend.get_job(repo_address=body.repo_address, job_id=body.job_id)


@router.get(
    "/{project_name}/jobs/list",
    dependencies=[Depends(Scope("jobs:list:read"))],
    response_model=List[Job],
)
async def list_job(project_name: str, body: JobsList):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    return backend.list_jobs(repo_address=body.repo_address, run_name=body.run_name)


@router.get(
    "/{project_name}/jobs/list/heads",
    dependencies=[Depends(Scope("jobs:list:read"))],
    response_model=List[JobHead],
)
async def list_heads_job(
    project_name: str, repo_address: RepoAddress, run_name: Optional[str] = None
):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    return backend.list_job_heads(repo_address=repo_address, run_name=run_name)


@router.post("/{project_name}/jobs/delete", dependencies=[Depends(Scope("jobs:delete:write"))])
async def delete_job(project_name: str, body: JobsGet):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    backend.delete_job_head(repo_address=body.repo_address, job_id=body.job_id)
