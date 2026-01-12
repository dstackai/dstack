import os
from typing import Annotated

import prometheus_client
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.server import settings
from dstack._internal.server.db import get_session
from dstack._internal.server.security.permissions import OptionalServiceAccount
from dstack._internal.server.services.prometheus import custom_metrics
from dstack._internal.server.utils.routers import error_not_found

_auth = OptionalServiceAccount(os.getenv("DSTACK_PROMETHEUS_AUTH_TOKEN"))

router = APIRouter(
    tags=["prometheus"],
    default_response_class=PlainTextResponse,
    dependencies=[Depends(_auth)],
)


@router.get("/metrics")
async def get_prometheus_metrics(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> str:
    # Note: Prometheus warns against storing high cardinality values in labels,
    # yet both client and custom metrics have labels like project, run, fleet, etc.
    # This may require a very big Prometheus server with lots of storage.
    if not settings.ENABLE_PROMETHEUS_METRICS:
        raise error_not_found()
    custom_metrics_ = await custom_metrics.get_metrics(session=session)
    client_metrics = prometheus_client.generate_latest().decode()
    return custom_metrics_ + client_metrics
