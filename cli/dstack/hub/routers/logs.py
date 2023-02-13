from typing import List, Union

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

from dstack.core.job import JobHead
from dstack.core.repo import RepoAddress
from dstack.hub.security.scope import Scope

router = APIRouter(prefix="/api/hub", tags=["logs"])

security = HTTPBearer()


@router.get("/{hub_name}/logs/poll", dependencies=[Depends(Scope("logs:poll:read"))])
async def poll_logs(
    hub_name: str,
    repo_address: RepoAddress,
    job_heads: List[JobHead],
    start_time: int,
    attached: bool,
):
    pass
