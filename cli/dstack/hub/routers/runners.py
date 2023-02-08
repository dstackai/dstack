from typing import List, Union

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer


from dstack.hub.security.scope import Scope
from dstack.hub.models import RepoAddress, RunHead, Job, JobHead

router = APIRouter(prefix="/api/hub", tags=["runners"])

security = HTTPBearer()


@router.post("/{hub_name}/runners/run", dependencies=[Depends(Scope("runners:run:write"))])
async def create_runners(hub_name: str, job: Job):
    pass


@router.get("/{hub_name}/runners/stop", dependencies=[Depends(Scope("runners:stop:write"))])
async def delete_runners(hub_name: str, repo_address: RepoAddress, job_id: str, abort: bool):
    pass

