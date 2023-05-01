from typing import List

from fastapi import APIRouter, Depends

from dstack.core.artifact import Artifact
from dstack.hub.models import ArtifactsList
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import get_project
from dstack.hub.security.permissions import ProjectMember

router = APIRouter(
    prefix="/api/project", tags=["artifacts"], dependencies=[Depends(ProjectMember())]
)


@router.post("/{project_name}/artifacts/list")
async def list_artifacts(project_name: str, body: ArtifactsList) -> List[Artifact]:
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    return backend.list_run_artifact_files(repo_id=body.repo_id, run_name=body.run_name)
