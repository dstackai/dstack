from fastapi import HTTPException, status

from dstack.hub.models import Project
from dstack.hub.repository.projects import ProjectManager


async def get_project(project_name: str) -> Project:
    hub = await ProjectManager.get(name=project_name)
    if hub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return hub
