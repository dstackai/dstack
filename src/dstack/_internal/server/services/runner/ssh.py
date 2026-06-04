import functools
from collections.abc import Mapping
from typing import Callable, List, Literal, Optional, TypeVar, Union

import requests
from typing_extensions import Concatenate, ParamSpec

from dstack._internal.core.errors import DstackError, SSHError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.runs import JobProvisioningData, JobRuntimeData
from dstack._internal.server.services.runner.client import LocalAddress
from dstack._internal.server.services.runner.pool import (
    InstanceConnection,
    PrivateKeyOrPair,
    instance_connection_pool,
)
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)
P = ParamSpec("P")
R = TypeVar("R")


def runner_ssh_tunnel(
    ports: List[int], retries: int = 3, retry_interval: float = 1
) -> Callable[
    [Callable[Concatenate[Mapping[int, LocalAddress], P], R]],
    Callable[
        Concatenate[PrivateKeyOrPair, JobProvisioningData, Optional[JobRuntimeData], P],
        Union[Literal[False], R],
    ],
]:
    """
    A decorator that opens an SSH tunnel to the runner instance for port forwarding.

    NOTE: connections from dstack-server to running jobs are expected to be short.
    The runner uses a heuristic to differentiate dstack-server connections from
    client connections based on their duration. See `ConnectionTracker` for details.
    """

    def decorator(
        func: Callable[Concatenate[Mapping[int, LocalAddress], P], R],
    ) -> Callable[
        Concatenate[PrivateKeyOrPair, JobProvisioningData, Optional[JobRuntimeData], P],
        Union[Literal[False], R],
    ]:
        @functools.wraps(func)
        def wrapper(
            ssh_private_key: PrivateKeyOrPair,
            job_provisioning_data: JobProvisioningData,
            job_runtime_data: Optional[JobRuntimeData],
            *args: P.args,
            **kwargs: P.kwargs,
        ) -> Union[Literal[False], R]:
            """
            Returns:
                is successful
            """
            if job_provisioning_data.backend == BackendType.LOCAL:
                # without SSH
                container_ports_map = {port: port for port in ports}
                return func(container_ports_map, *args, **kwargs)

            if not job_provisioning_data.dockerized:
                # Connections from dstack-server to runner's sshd are expected to be short
                # as the `inactivity_duration` feature distinguishes user and server connections based on duration.
                # Do not re-use SSH connections for container-based backends.
                # TODO: Drop `inactivity_duration` dependence on connection duration and re-use connections.
                conn = InstanceConnection(
                    ssh_private_key=ssh_private_key,
                    jpd=job_provisioning_data,
                    jrd=job_runtime_data,
                    ephemeral=True,
                )
                try:
                    conn.open()
                except SSHError:
                    return False
                try:
                    return func({p: conn.forwarded_path(p) for p in ports}, *args, **kwargs)
                except (DstackError, requests.RequestException):
                    return False
                finally:
                    conn.close()

            for attempt in range(2):  # cached, then one fresh reopen
                conn = instance_connection_pool.get_or_open(
                    ssh_private_key=ssh_private_key,
                    jpd=job_provisioning_data,
                    jrd=job_runtime_data,
                )
                if conn is None:
                    return False  # couldn't establish at all
                try:
                    return func({p: conn.forwarded_path(p) for p in ports}, *args, **kwargs)
                except (SSHError, requests.ConnectionError):
                    instance_connection_pool.drop(conn.key)  # dead ssh connection, re-open
                except (DstackError, requests.RequestException):
                    return False  # reached runner, app-level fail; don't re-open ssh connection
            return False

        return wrapper

    return decorator
