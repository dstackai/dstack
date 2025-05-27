import logging
import os

import uvicorn
from fastapi import FastAPI

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
from example_plugin_server.utils import configure_logging

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
    response = FleetSpecResponse(spec=request.spec, error=None)
    return response


@app.post("/apply_policies/on_volume_apply")
async def on_volume_apply(request: VolumeSpecRequest) -> VolumeSpecResponse:
    logger.info(
        f"Received volume spec request from user {request.user} and project {request.project}"
    )
    response = VolumeSpecResponse(spec=request.spec, error=None)
    return response


@app.post("/apply_policies/on_gateway_apply")
async def on_gateway_apply(request: GatewaySpecRequest) -> GatewaySpecResponse:
    logger.info(
        f"Received gateway spec request from user {request.user} and project {request.project}"
    )
    response = GatewaySpecResponse(spec=request.spec, error=None)
    return response


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.getenv("DSTACK_REST_PLUGIN_SERVER_PORT", 8000)),
    )
