from typing import List, Union

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

from dstack.core.job import Job
from dstack.core.repo import RepoAddress
from dstack.hub.models import StopRunners
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import get_project
from dstack.hub.security.scope import Scope

router = APIRouter(prefix="/api/project", tags=["runners"])

security = HTTPBearer()


@router.post("/{project_name}/runners/run", dependencies=[Depends(Scope("runners:run:write"))])
async def run_runners(project_name: str, job: Job):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    backend.run_job(job=job)


@router.post("/{project_name}/runners/stop", dependencies=[Depends(Scope("runners:stop:write"))])
async def stop_runners(project_name: str, body: StopRunners):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    backend.stop_job(repo_address=body.repo_address, job_id=body.job_id, abort=body.abort)
