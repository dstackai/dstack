"""Private management API: exposed only through the server's SSH connection."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from dstack._internal.proxy.gateway.deps import get_metering, get_nginx
from dstack._internal.proxy.gateway.services.metering import MeteringCollector
from dstack._internal.proxy.gateway.services.nginx import Nginx
from dstack._internal.proxy.lib.schemas.usage import (
    UsageAckRequest,
    UsageAckResponse,
    UsageBatchPage,
    UsageDrainResponse,
)

router = APIRouter()


@router.post("/drain", response_model=UsageDrainResponse)
async def drain_usage(
    metering: Annotated[MeteringCollector, Depends(get_metering)],
    nginx: Annotated[Nginx, Depends(get_nginx)],
) -> UsageDrainResponse:
    # Record where a process crash can interrupt active requests before changing ingress.
    await metering.drain(ingress_idle=False)
    if not await nginx.drain():
        return UsageDrainResponse(sealed=False, empty=False)
    return await metering.drain()


@router.get("/batches", response_model=UsageBatchPage)
async def get_batches(
    metering: Annotated[MeteringCollector, Depends(get_metering)],
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> UsageBatchPage:
    return await metering.get_batches(limit)


@router.post("/batches/ack", response_model=UsageAckResponse)
async def acknowledge_batches(
    body: UsageAckRequest,
    metering: Annotated[MeteringCollector, Depends(get_metering)],
) -> UsageAckResponse:
    return await metering.acknowledge(body.batch_ids)
