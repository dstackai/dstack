import logging

from fastapi import FastAPI

from app.utils import configure_logging
from dstack.plugins.builtin.rest_plugin import (
    FleetSpecRequest,
    FleetSpecResponse,
    GatewaySpecRequest,
    GatewaySpecResponse,
    RunSpecRequest,
    RunSpecResponse,
    VolumeSpecRequest,
    VolumeSpecResponse,
)

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI()


@app.post("/apply_policies/on_run_apply")
async def on_run_apply(request: RunSpecRequest) -> RunSpecResponse:
    logger.info(
        f"Received run spec request from user {request.user} and project {request.project}"
    )
    response = RunSpecResponse(spec=request.spec, error=None)
    return response


@app.post("/apply_policies/on_fleet_apply")
async def on_fleet_apply(request: FleetSpecRequest) -> FleetSpecResponse:
    logger.info(
        f"Received fleet spec request from user {request.user} and project {request.project}"
    )
    response = FleetSpecResponse(request.spec, error=None)
    return response


@app.post("/apply_policies/on_volume_apply")
async def on_volume_apply(request: VolumeSpecRequest) -> VolumeSpecResponse:
    logger.info(
        f"Received volume spec request from user {request.user} and project {request.project}"
    )
    response = VolumeSpecResponse(request.spec, error=None)
    return response


@app.post("/apply_policies/on_gateway_apply")
async def on_gateway_apply(request: GatewaySpecRequest) -> GatewaySpecResponse:
    logger.info(
        f"Received gateway spec request from user {request.user} and project {request.project}"
    )
    response = GatewaySpecResponse(request.spec, error=None)
    return response
