from typing import List, Union

from fastapi import APIRouter, Depends

from dstack.core.artifact import Artifact
from dstack.core.repo import RepoAddress
from dstack.hub.models import ArtifactsList
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import get_project
from dstack.hub.security.scope import Scope

router = APIRouter(prefix="/api/project", tags=["artifacts"])


@router.get(
    "/{project_name}/artifacts/list",
    dependencies=[Depends(Scope("artifacts:list:read"))],
    response_model=List[Artifact],
)
async def list_artifacts(project_name: str, body: ArtifactsList):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    return backend.list_run_artifact_files(repo_address=body.repo_address, run_name=body.run_name)


@router.get(
    "/{project_name}/artifacts/download", dependencies=[Depends(Scope("artifacts:download:read"))]
)
async def download_artifacts(
    project_name: str,
    repo_address: RepoAddress,
    run_name: str,
    output_dir: Union[str, None] = None,
    output_job_dirs: bool = True,
):
    pass


@router.post(
    "/{project_name}/artifacts/upload", dependencies=[Depends(Scope("artifacts:upload:write"))]
)
async def upload_artifacts(
    project_name: str,
    repo_address: RepoAddress,
    job_id: str,
    artifact_name: str,
    local_path: str,
):
    pass
