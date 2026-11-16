"""Private management API: exposed only through the server's SSH connection."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from dstack._internal.proxy.gateway.deps import get_metering
from dstack._internal.proxy.gateway.services.metering import MeteringCollector
from dstack._internal.proxy.lib.schemas.usage import (
    UsageAckRequest,
    UsageAckResponse,
    UsageBatchPage,
)

router = APIRouter()


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
