import asyncio
from typing import List, Optional

from dstack._internal.core.error import NoGatewayError
from dstack._internal.core.gateway import Gateway
from dstack._internal.core.job import Job
from dstack._internal.hub.db.models import Project
from dstack._internal.hub.routers.util import call_backend
from dstack._internal.hub.services.common import get_backends


async def list_gateways(project: Project) -> List[Gateway]:
    backends = await get_backends(project)
    tasks = [call_backend(backend.list_gateways) for _, backend in backends]
    gateways = []
    for (_, backend), backend_gateways in zip(backends, await asyncio.gather(*tasks)):
        for gateway in backend_gateways:
            gateways.append(
                Gateway(
                    backend=backend.name,
                    head=gateway,
                    default=gateway.instance_name == project.default_gateway,
                )
            )
    return gateways


async def get_gateway(project: Project, instance_name: str) -> Optional[Gateway]:
    gateways = await list_gateways(project)
    for gateway in gateways:
        if gateway.head.instance_name == instance_name:
            return gateway
    return None


async def setup_job_gateway(project: Project, job: Job):
    if job.gateway.gateway_name is None:
        job.gateway.gateway_name = project.default_gateway
    if job.gateway.gateway_name is None:
        raise NoGatewayError("No default gateway is set")
    gateway = await get_gateway(project, job.gateway.gateway_name)
    if gateway is None:
        raise NoGatewayError(f"No gateway {job.gateway.gateway_name}")

    if gateway.head.wildcard_domain:
        job.gateway.secure = True
        job.gateway.hostname = f"{job.run_name}.{gateway.head.wildcard_domain[2:]}"  # strip *.
        job.gateway.public_port = 443
    else:
        job.gateway.secure = False
        job.gateway.hostname = gateway.head.external_ip
