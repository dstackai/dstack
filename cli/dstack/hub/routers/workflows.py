from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

from dstack.hub.models import UserRepoAddress
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import get_project
from dstack.hub.security.scope import Scope

router = APIRouter(prefix="/api/project", tags=["workflows"])

security = HTTPBearer()


@router.post(
    "/{project_name}/workflows/{workflow_name}/cache/delete",
    dependencies=[Depends(Scope("workflows:delete:write"))],
)
async def delete_secrets(project_name: str, workflow_name: str, user_repo: UserRepoAddress):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    backend.delete_workflow_cache(
        repo_address=user_repo.repo_address,
        username=user_repo.username,
        workflow_name=workflow_name,
    )
