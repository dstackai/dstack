from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from dstack._internal.core.job import Job, JobHead
from dstack._internal.hub.routers.util import call_backend, error_detail, get_project
from dstack._internal.hub.schemas import JobHeadList, JobsGet, JobsList
from dstack._internal.hub.security.permissions import ProjectMember
from dstack._internal.hub.services.common import get_backends

router = APIRouter(prefix="/api/project", tags=["jobs"], dependencies=[Depends(ProjectMember())])


@router.post("/{project_name}/jobs/get")
async def get_job(project_name: str, body: JobsGet) -> Job:
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)
    for _, backend in backends:
        job = await call_backend(backend.get_job, body.repo_id, body.job_id)
        if job is not None:
            return job
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=error_detail(msg=f"Job not found"),
    )


@router.post("/{project_name}/jobs/list")
async def list_jobs(project_name: str, body: JobsList) -> List[Job]:
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)
    jobs = []
    for _, backend in backends:
        jobs += await call_backend(backend.list_jobs, body.repo_id, body.run_name)
    return jobs


@router.post("/{project_name}/jobs/list/heads")
async def list_job_heads(project_name: str, body: JobHeadList) -> List[JobHead]:
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)
    job_heads = []
    for _, backend in backends:
        job_heads += await call_backend(backend.list_job_heads, body.repo_id, body.run_name)
    return job_heads


@router.post("/{project_name}/jobs/delete")
async def delete_job(project_name: str, body: JobsGet):
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)
    for _, backend in backends:
        await call_backend(backend.delete_job_head, body.repo_id, body.job_id)
