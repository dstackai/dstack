"""SSH tunnel to a job replica's service port, exposed as a local Unix domain socket."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

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
_REPLICA_SOCKET_NAME = "replica.sock"


@asynccontextmanager
async def get_service_replica_tunnel(job: JobModel) -> AsyncGenerator[Path, None]:
    options = {
        **SSH_DEFAULT_OPTIONS,
        "ConnectTimeout": str(int(SSH_CONNECT_TIMEOUT.total_seconds())),
    }
    job_spec = get_job_spec(job)
    with TemporaryDirectory() as temp_dir:
        app_socket_path = (Path(temp_dir) / _REPLICA_SOCKET_NAME).absolute()
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
            yield app_socket_path
