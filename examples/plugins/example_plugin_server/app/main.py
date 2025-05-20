import logging

from fastapi import FastAPI

from app.models import FleetSpecRequest, GatewaySpecRequest, RunSpecRequest, VolumeSpecRequest
from app.utils import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI()


@app.post("/apply_policies/on_run_apply")
async def on_run_apply(request: RunSpecRequest):
    logger.info(
        f"Received run spec request from user {request.user} and project {request.project}"
    )
    return request.spec


@app.post("/apply_policies/on_fleet_apply")
async def on_fleet_apply(request: FleetSpecRequest):
    logger.info(
        f"Received fleet spec request from user {request.user} and project {request.project}"
    )
    return request.spec


@app.post("/apply_policies/on_volume_apply")
async def on_volume_apply(request: VolumeSpecRequest):
    logger.info(
        f"Received volume spec request from user {request.user} and project {request.project}"
    )
    return request.spec


@app.post("/apply_policies/on_gateway_apply")
async def on_gateway_apply(request: GatewaySpecRequest):
    logger.info(
        f"Received gateway spec request from user {request.user} and project {request.project}"
    )
    return request.spec
