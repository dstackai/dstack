from typing import List, Optional

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

from dstack.core.job import Job, JobHead
from dstack.core.repo import RepoAddress
from dstack.hub.models import JobsGet, JobsList
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import get_hub
from dstack.hub.security.scope import Scope

router = APIRouter(prefix="/api/hub", tags=["jobs"])

security = HTTPBearer()


@router.post("/{hub_name}/jobs/create", dependencies=[Depends(Scope("jobs:create:write"))])
async def create_job(hub_name: str, job: Job):
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    backend.create_job(job=job)


@router.get(
    "/{hub_name}/jobs/get", dependencies=[Depends(Scope("jobs:get:read"))], response_model=Job
)
async def get_job(hub_name: str, body: JobsGet):
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    return backend.get_job(repo_address=body.repo_address, job_id=body.job_id)


@router.get(
    "/{hub_name}/jobs/list",
    dependencies=[Depends(Scope("jobs:list:read"))],
    response_model=List[Job],
)
async def list_job(hub_name: str, body: JobsList):
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    return backend.list_jobs(repo_address=body.repo_address, run_name=body.run_name)


@router.get(
    "/{hub_name}/jobs/list/heads",
    dependencies=[Depends(Scope("jobs:list:read"))],
    response_model=List[JobHead],
)
async def list_heads_job(hub_name: str, repo_address: RepoAddress, run_name: Optional[str] = None):
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    return backend.list_job_heads(repo_address=repo_address, run_name=run_name)


@router.post("/{hub_name}/jobs/delete", dependencies=[Depends(Scope("jobs:delete:write"))])
async def delete_job(hub_name: str, body: JobsGet):
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    backend.delete_job_head(repo_address=body.repo_address, job_id=body.job_id)
