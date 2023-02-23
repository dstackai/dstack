from typing import List, Union

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

from dstack.core.job import Job
from dstack.core.repo import RepoAddress
from dstack.hub.models import StopRunners
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import get_hub
from dstack.hub.security.scope import Scope

router = APIRouter(prefix="/api/hub", tags=["runners"])

security = HTTPBearer()


@router.post("/{hub_name}/runners/run", dependencies=[Depends(Scope("runners:run:write"))])
async def run_runners(hub_name: str, job: Job):
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    backend.run_job(job=job)


@router.post("/{hub_name}/runners/stop", dependencies=[Depends(Scope("runners:stop:write"))])
async def stop_runners(hub_name: str, body: StopRunners):
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    backend.stop_job(repo_address=body.repo_address, job_id=body.job_id, abort=body.abort)
