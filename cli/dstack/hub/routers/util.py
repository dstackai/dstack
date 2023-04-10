from typing import Dict, Optional

from fastapi import HTTPException, status

from dstack.hub.models import Project
from dstack.hub.repository.projects import ProjectManager


async def get_project(project_name: str) -> Project:
    hub = await ProjectManager.get(name=project_name)
    if hub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("Project not found"),
        )
    return hub


def error_detail(msg: str, code: Optional[str] = None, **kwargs) -> Dict:
    return {
        "msg": msg,
        "code": code,
        **kwargs,
    }
