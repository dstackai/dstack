from typing import List

from fastapi import APIRouter, Depends

from dstack._internal.core.job import Job, JobHead
from dstack._internal.hub.db.models import User
from dstack._internal.hub.models import JobHeadList, JobsGet, JobsList
from dstack._internal.hub.routers.util import call_backend, get_backend, get_project
from dstack._internal.hub.security.permissions import Authenticated, ProjectMember

router = APIRouter(prefix="/api/project", tags=["jobs"], dependencies=[Depends(ProjectMember())])


@router.post("/{project_name}/jobs/create")
async def create_job(project_name: str, job: Job, user: User = Depends(Authenticated())) -> Job:
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    job.hub_user_name = user.name
    await call_backend(backend.create_job, job)
    return job


@router.post("/{project_name}/jobs/get")
async def get_job(project_name: str, body: JobsGet) -> Job:
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    job = await call_backend(backend.get_job, body.repo_id, body.job_id)
    return job


@router.post("/{project_name}/jobs/list")
async def list_job(project_name: str, body: JobsList) -> List[Job]:
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    jobs = await call_backend(backend.list_jobs, body.repo_id, body.run_name)
    return jobs


@router.post("/{project_name}/jobs/list/heads")
async def list_job_heads(project_name: str, body: JobHeadList) -> List[JobHead]:
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    job_heads = await call_backend(backend.list_job_heads, body.repo_id, body.run_name)
    return job_heads


@router.post("/{project_name}/jobs/delete")
async def delete_job(project_name: str, body: JobsGet):
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    await call_backend(backend.delete_job_head, body.repo_id, body.job_id)
