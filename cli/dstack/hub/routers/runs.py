from typing import List, Union

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer


from dstack.hub.security.scope import Scope
from dstack.core.repo import RepoAddress
from dstack.hub.routers.util import get_hub
from dstack.hub.routers.cache import get_backend
from dstack.core.run import RunHead

router = APIRouter(prefix="/api/hub", tags=["runs"])

security = HTTPBearer()


@router.post("/{hub_name}/runs/create", dependencies=[Depends(Scope("runs:create:write"))], response_model=str)
async def create_run(hub_name: str, repo_address: RepoAddress) -> str:
    hub = await get_hub(hub_name=hub_name)
    backend = get_backend(hub)
    run_name = backend.create_run(repo_address=repo_address)
    return run_name


@router.get("/{hub_name}/runs/list", dependencies=[Depends(Scope("runs:create:read"))], response_model=List[RunHead])
async def list_run(hub_name: str, repo_address: RepoAddress, include_request_heads: bool = True, run_name: Union[str, None] = None):
    pass
