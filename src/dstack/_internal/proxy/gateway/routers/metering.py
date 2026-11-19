from typing import Annotated

from fastapi import APIRouter, Depends

from dstack._internal.proxy.gateway.deps import get_gateway_proxy_meter
from dstack._internal.proxy.gateway.schemas.metering import (
    CollectMeteringRequest,
    CollectMeteringResponse,
)
from dstack._internal.proxy.gateway.services.metering import GatewayProxyMeter

router = APIRouter()


@router.post("/collect")
async def collect_metering(
    body: CollectMeteringRequest,
    meter: Annotated[GatewayProxyMeter, Depends(get_gateway_proxy_meter)],
) -> CollectMeteringResponse:
    return CollectMeteringResponse(batches=await meter.collect(after=body.after, limit=body.limit))
