from typing import List, Union

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

from dstack.hub.models import RepoAddress, RunHead
from dstack.hub.security.scope import Scope

router = APIRouter(prefix="/api/hub", tags=["runs"])

security = HTTPBearer()


@router.post("/{hub_name}/runs/create", dependencies=[Depends(Scope("runs:create:write"))])
async def create_run(hub_name: str, repos: RepoAddress):
    pass


@router.get(
    "/{hub_name}/runs/list",
    dependencies=[Depends(Scope("runs:create:read"))],
    response_model=List[RunHead],
)
async def list_run(
    hub_name: str,
    repo_address: RepoAddress,
    include_request_heads: bool = True,
    run_name: Union[str, None] = None,
):
    pass
