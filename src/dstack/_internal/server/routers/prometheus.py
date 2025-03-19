from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.server import settings
from dstack._internal.server.db import get_session
from dstack._internal.server.deps import Project
from dstack._internal.server.models import ProjectModel
from dstack._internal.server.services import prometheus
from dstack._internal.server.utils.routers import error_not_found

router = APIRouter(
    tags=["prometheus"],
    default_response_class=PlainTextResponse,
)


@router.get("/metrics")
async def get_prometheus_metrics(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> str:
    if not settings.ENABLE_PROMETHEUS_METRICS:
        raise error_not_found()
    return await prometheus.get_metrics(session=session)


@router.get("/metrics/project/{project_name}", deprecated=True)
async def get_project_prometheus_metrics(
    session: Annotated[AsyncSession, Depends(get_session)],
    project: Annotated[ProjectModel, Depends(Project())],
) -> str:
    if not settings.ENABLE_PROMETHEUS_METRICS:
        raise error_not_found()
    return await prometheus.get_project_metrics(session=session, project=project)
