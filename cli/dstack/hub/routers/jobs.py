from typing import List, Union

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer


from dstack.hub.security.scope import Scope
from dstack.hub.models import RepoAddress, RunHead, Job, JobHead

router = APIRouter(prefix="/api/hub", tags=["jobs"])

security = HTTPBearer()


@router.post("/{hub_name}/jobs/create", dependencies=[Depends(Scope("jobs:create:write"))])
async def create_job(hub_name: str, job: Job):
    pass


@router.get("/{hub_name}/jobs/get", dependencies=[Depends(Scope("jobs:get:read"))], response_model=Job)
async def get_job(hub_name: str, repo_address: RepoAddress, job_id: str):
    pass


@router.get("/{hub_name}/jobs/list", dependencies=[Depends(Scope("jobs:list:read"))], response_model=List[Job])
async def list_job(hub_name: str, repo_address: RepoAddress, run_name: str):
    pass


@router.get("/{hub_name}/jobs/list/heads", dependencies=[Depends(Scope("jobs:list:read"))], response_model=List[JobHead])
async def list_heads_job(hub_name: str, repo_address: RepoAddress, run_name: str):
    pass


@router.get("/{hub_name}/jobs/delete", dependencies=[Depends(Scope("jobs:delete:write"))])
async def delete_job(hub_name: str, repo_address: RepoAddress, job_id: str):
    pass
