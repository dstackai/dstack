from typing import List, Union

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

from dstack.core.artifact import Artifact
from dstack.core.repo import RepoAddress
from dstack.hub.models import Artifact, RepoAddress
from dstack.hub.security.scope import Scope

router = APIRouter(prefix="/api/hub", tags=["artifacts"])

security = HTTPBearer()


@router.get(
    "/{hub_name}/artifacts/list",
    dependencies=[Depends(Scope("artifacts:list:read"))],
    response_model=List[Artifact],
)
async def list_artifacts(hub_name: str, repo_address: RepoAddress, run_name: str):
    pass


@router.get(
    "/{hub_name}/artifacts/download", dependencies=[Depends(Scope("artifacts:download:read"))]
)
async def download_artifacts(
    hub_name: str,
    repo_address: RepoAddress,
    run_name: str,
    output_dir: Union[str, None] = None,
    output_job_dirs: bool = True,
):
    pass


@router.post(
    "/{hub_name}/artifacts/upload", dependencies=[Depends(Scope("artifacts:upload:write"))]
)
async def upload_artifacts(
    hub_name: str,
    repo_address: RepoAddress,
    job_id: str,
    artifact_name: str,
    local_path: str,
):
    pass
