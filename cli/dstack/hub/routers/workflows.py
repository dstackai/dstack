from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

from dstack.core.repo import RepoRef
from dstack.hub.db.models import User
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import get_project
from dstack.hub.security.permissions import Authenticated, ProjectMember

router = APIRouter(
    prefix="/api/project", tags=["workflows"], dependencies=[Depends(ProjectMember())]
)

security = HTTPBearer()


@router.post("/{project_name}/workflows/{workflow_name}/cache/delete")
async def delete_workflow_cache(
    project_name: str, workflow_name: str, repo_ref: RepoRef, user: User = Depends(Authenticated())
):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    backend.delete_workflow_cache(repo_ref.repo_id, user.name, workflow_name=workflow_name)
