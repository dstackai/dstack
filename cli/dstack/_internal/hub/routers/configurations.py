from fastapi import APIRouter, Depends

from dstack._internal.core.repo import RepoRef
from dstack._internal.hub.db.models import User
from dstack._internal.hub.routers.util import call_backend, get_project
from dstack._internal.hub.security.permissions import Authenticated, ProjectMember
from dstack._internal.hub.services.common import get_backends

router = APIRouter(
    prefix="/api/project", tags=["configurations"], dependencies=[Depends(ProjectMember())]
)


@router.post("/{project_name}/configurations/{configuration_path:path}/cache/delete")
async def delete_configuration_cache(
    project_name: str,
    configuration_path: str,
    repo_ref: RepoRef,
    user: User = Depends(Authenticated()),
):
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)
    for _, backend in backends:
        await call_backend(
            backend.delete_configuration_cache, repo_ref.repo_id, user.name, configuration_path
        )
