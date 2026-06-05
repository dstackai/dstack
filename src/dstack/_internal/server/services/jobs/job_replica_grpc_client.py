"""SSH-tunneled gRPC channel target to a job's service port (UDS)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import grpc

from dstack._internal.core.services.ssh.tunnel import (
    SSH_DEFAULT_OPTIONS,
    IPSocket,
    SocketPair,
    UnixSocket,
)
from dstack._internal.server.models import JobModel
from dstack._internal.server.services.jobs import get_job_spec
from dstack._internal.server.services.ssh import container_ssh_tunnel
from dstack._internal.utils.common import get_or_error

SSH_CONNECT_TIMEOUT = timedelta(seconds=10)
# Match router_worker_sync HTTP server_info cap (_MAX_SERVER_INFO_RESPONSE_BYTES).
_MAX_GRPC_MESSAGE_BYTES = 256 * 1024
_GRPC_CHANNEL_OPTIONS = (
    ("grpc.max_receive_message_length", _MAX_GRPC_MESSAGE_BYTES),
    ("grpc.max_send_message_length", _MAX_GRPC_MESSAGE_BYTES),
)


@asynccontextmanager
async def get_service_replica_grpc_client(job: JobModel) -> AsyncGenerator[Any, None]:
    options = {
        **SSH_DEFAULT_OPTIONS,
        "ConnectTimeout": str(int(SSH_CONNECT_TIMEOUT.total_seconds())),
    }
    job_spec = get_job_spec(job)
    with TemporaryDirectory() as temp_dir:
        # Keep the same socket file name as the HTTP helper for consistency.
        app_socket_path = (Path(temp_dir) / "replica.sock").absolute()
        async with container_ssh_tunnel(
            job=job,
            forwarded_sockets=[
                SocketPair(
                    remote=IPSocket("localhost", get_or_error(job_spec.service_port)),
                    local=UnixSocket(app_socket_path),
                ),
            ],
            options=options,
        ):
            target = f"unix://{app_socket_path}"
            channel = grpc.aio.insecure_channel(target, options=_GRPC_CHANNEL_OPTIONS)
            try:
                yield channel
            finally:
                await channel.close()
