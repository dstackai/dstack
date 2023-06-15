from fastapi import APIRouter, Depends

from dstack._internal.core.repo import RepoRef
from dstack._internal.hub.db.models import User
from dstack._internal.hub.routers.cache import get_backend
from dstack._internal.hub.routers.util import get_project
from dstack._internal.hub.security.permissions import Authenticated, ProjectMember
from dstack._internal.hub.utils.common import run_async

router = APIRouter(
    prefix="/api/project", tags=["workflows"], dependencies=[Depends(ProjectMember())]
)


@router.post("/{project_name}/workflows/{workflow_name}/cache/delete")
async def delete_workflow_cache(
    project_name: str, workflow_name: str, repo_ref: RepoRef, user: User = Depends(Authenticated())
):
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    await run_async(backend.delete_workflow_cache, repo_ref.repo_id, user.name, workflow_name)
