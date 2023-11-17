from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel
from dstack._internal.server.services.projects import get_project_model_by_name
from dstack._internal.server.utils.routers import error_not_found


class Project:
    async def __call__(
        self,
        project_name: str,
        session: AsyncSession = Depends(get_session),
    ) -> ProjectModel:
        project = await get_project_model_by_name(session=session, project_name=project_name)
        if project is None:
            raise error_not_found()
        return project
