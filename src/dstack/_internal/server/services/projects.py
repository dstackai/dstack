from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.server.models import ProjectModel


async def get_project_model_by_name(
    session: AsyncSession,
    project_name: str,
) -> Optional[ProjectModel]:
    res = await session.execute(select(ProjectModel).where(ProjectModel.name == project_name))
    return res.scalar()
