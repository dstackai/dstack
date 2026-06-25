"""SSH-tunneled gRPC channel target to a job's service port (UDS)."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import grpc

from dstack._internal.server.models import JobModel
from dstack._internal.server.services.jobs.job_replica_tunnel import get_service_replica_tunnel

# Match router_worker_sync HTTP server_info cap (_MAX_SERVER_INFO_RESPONSE_BYTES).
_MAX_GRPC_MESSAGE_BYTES = 256 * 1024
_GRPC_CHANNEL_OPTIONS = (
    ("grpc.max_receive_message_length", _MAX_GRPC_MESSAGE_BYTES),
    ("grpc.max_send_message_length", _MAX_GRPC_MESSAGE_BYTES),
)


@asynccontextmanager
async def get_service_replica_grpc_channel_over_uds(
    uds_path: Path,
) -> AsyncGenerator[Any, None]:
    target = f"unix://{uds_path}"
    channel = grpc.aio.insecure_channel(target, options=_GRPC_CHANNEL_OPTIONS)
    try:
        yield channel
    finally:
        await channel.close()


@asynccontextmanager
async def get_service_replica_grpc_client(job: JobModel) -> AsyncGenerator[Any, None]:
    async with get_service_replica_tunnel(job) as uds_path:
        async with get_service_replica_grpc_channel_over_uds(uds_path) as channel:
            yield channel
