"""SSH-tunneled async HTTP client to a job's service port (same path as probes)."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from httpx import AsyncClient, AsyncHTTPTransport

from dstack._internal.server.models import JobModel
from dstack._internal.server.services.jobs.job_replica_tunnel import get_service_replica_tunnel


@asynccontextmanager
async def get_service_replica_http_client_over_uds(
    uds_path: Path,
) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=AsyncHTTPTransport(uds=str(uds_path))) as client:
        yield client


@asynccontextmanager
async def get_service_replica_client(
    job: JobModel,
) -> AsyncGenerator[AsyncClient, None]:
    async with get_service_replica_tunnel(job) as uds_path:
        async with get_service_replica_http_client_over_uds(uds_path) as client:
            yield client
