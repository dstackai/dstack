from typing import List, Tuple

from fastapi import APIRouter, Depends

from dstack._internal.core.models.templates import UITemplate
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.security.permissions import ProjectMember
from dstack._internal.server.services import templates as templates_service
from dstack._internal.server.utils.routers import CustomORJSONResponse

router = APIRouter(
    prefix="/api/project/{project_name}/templates",
    tags=["templates"],
)


@router.post("/list", response_model=List[UITemplate])
async def list_templates(
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    return CustomORJSONResponse(await templates_service.list_templates())
