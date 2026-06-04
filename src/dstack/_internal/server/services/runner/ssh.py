import functools
import time
from collections.abc import Mapping
from typing import Callable, Literal, Optional, TypeVar, Union

import requests
from typing_extensions import Concatenate, ParamSpec

from dstack._internal.core.errors import DstackError, SSHError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.runs import JobProvisioningData, JobRuntimeData
from dstack._internal.server import settings
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
    retries: int = 3, retry_interval: float = 1
) -> Callable[
    [Callable[Concatenate[Mapping[int, LocalAddress], P], R]],
    Callable[
        Concatenate[PrivateKeyOrPair, JobProvisioningData, Optional[JobRuntimeData], P],
        Union[Literal[False], R],
    ],
]:
    """
    A decorator that opens an SSH tunnel to the runner instance for port forwarding.

    Forwarded ports:
    * VM-based backends: forward the shim and runner ports.
    * Container-based backends: forward only the runner port.
    * `jrd.ports` may remap the runner port (blocks case).

    Always forwards the same ports for the given instance/job so that connection is reused across all calls.
    In case of blocks, each job uses a separate connection as the runner host port differs.

    `retries` and `retry_interval` apply only if connection pooling is not used.
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
                port_map = InstanceConnection.get_container_to_host_port_map(
                    job_provisioning_data, job_runtime_data
                )
                return func(port_map, *args, **kwargs)

            if settings.SERVER_SSH_POOL_DISABLED or not job_provisioning_data.dockerized:
                # Connections from dstack-server to runner's sshd are expected to be short
                # as the `inactivity_duration` feature distinguishes user and server connections based on duration.
                # Do not re-use SSH connections for container-based backends.
                # TODO: Drop `inactivity_duration` dependence on connection duration and re-use connections.
                for attempt in range(retries):
                    if attempt > 0:
                        time.sleep(retry_interval)
                    conn = InstanceConnection(
                        ssh_private_key=ssh_private_key,
                        jpd=job_provisioning_data,
                        jrd=job_runtime_data,
                        ephemeral=True,
                    )
                    try:
                        conn.open()
                    except SSHError:
                        continue
                    try:
                        return func(conn.forwarded_paths(), *args, **kwargs)
                    except (SSHError, requests.ConnectionError):
                        continue  # connection-level failure, retry with a fresh connection
                    except (DstackError, requests.RequestException):
                        return False
                    finally:
                        conn.close()
                return False

            for _ in range(2):  # cached, then one fresh reopen
                conn = instance_connection_pool.get_or_open(
                    ssh_private_key=ssh_private_key,
                    jpd=job_provisioning_data,
                    jrd=job_runtime_data,
                )
                if conn is None:
                    return False  # couldn't establish at all
                try:
                    return func(conn.forwarded_paths(), *args, **kwargs)
                except (SSHError, requests.ConnectionError):
                    instance_connection_pool.drop(conn.key)  # dead ssh connection, re-open
                except (DstackError, requests.RequestException):
                    return False  # reached runner, app-level fail; don't re-open ssh connection
            return False

        return wrapper

    return decorator
