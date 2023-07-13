from typing import List

from fastapi import APIRouter, Depends

from dstack._internal.core.artifact import Artifact
from dstack._internal.hub.models import ArtifactsList
from dstack._internal.hub.routers.util import get_backend, get_project
from dstack._internal.hub.security.permissions import ProjectMember
from dstack._internal.hub.utils.common import run_async

router = APIRouter(
    prefix="/api/project", tags=["artifacts"], dependencies=[Depends(ProjectMember())]
)


@router.post("/{project_name}/artifacts/list")
async def list_artifacts(project_name: str, body: ArtifactsList) -> List[Artifact]:
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    artifacts = await run_async(
        backend.list_run_artifact_files,
        body.repo_id,
        body.run_name,
        body.prefix,
        body.recursive,
    )
    return artifacts
