import functools
import socket
import time
from collections.abc import Iterable
from typing import Callable, Dict, List, Optional, TypeVar, Union

import requests
from typing_extensions import Concatenate, ParamSpec

from dstack._internal.core.errors import DstackError, SSHError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.runs import JobProvisioningData, JobRuntimeData
from dstack._internal.core.services.ssh.tunnel import SSHTunnel, ports_to_forwarded_sockets
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import FileContent

logger = get_logger(__name__)
P = ParamSpec("P")
R = TypeVar("R")
# A host private key or pair of (host private key, optional proxy jump private key)
PrivateKeyOrPair = Union[str, tuple[str, Optional[str]]]


def runner_ssh_tunnel(
    ports: List[int], retries: int = 3, retry_interval: float = 1
) -> Callable[
    [Callable[Concatenate[Dict[int, int], P], R]],
    Callable[
        Concatenate[PrivateKeyOrPair, JobProvisioningData, Optional[JobRuntimeData], P],
        Union[bool, R],
    ],
]:
    """
    A decorator that opens an SSH tunnel to the runner.

    NOTE: connections from dstack-server to running jobs are expected to be short.
    The runner uses a heuristic to differentiate dstack-server connections from
    client connections based on their duration. See `ConnectionTracker` for details.
    """

    def decorator(
        func: Callable[Concatenate[Dict[int, int], P], R],
    ) -> Callable[
        Concatenate[PrivateKeyOrPair, JobProvisioningData, Optional[JobRuntimeData], P],
        Union[bool, R],
    ]:
        @functools.wraps(func)
        def wrapper(
            ssh_private_key: PrivateKeyOrPair,
            job_provisioning_data: JobProvisioningData,
            job_runtime_data: Optional[JobRuntimeData],
            *args: P.args,
            **kwargs: P.kwargs,
        ) -> Union[bool, R]:
            """
            Returns:
                is successful
            """
            # container:host mapping
            container_ports_map = {port: port for port in ports}
            if job_runtime_data is not None and job_runtime_data.ports is not None:
                container_ports_map.update(job_runtime_data.ports)

            if job_provisioning_data.backend == BackendType.LOCAL:
                # without SSH
                return func(container_ports_map, *args, **kwargs)

            if isinstance(ssh_private_key, str):
                ssh_proxy_private_key = None
            else:
                ssh_private_key, ssh_proxy_private_key = ssh_private_key
            identity = FileContent(ssh_private_key)
            if ssh_proxy_private_key is not None:
                proxy_identity = FileContent(ssh_proxy_private_key)
            else:
                proxy_identity = None

            ssh_proxies = []
            if job_provisioning_data.ssh_proxy is not None:
                ssh_proxies.append((job_provisioning_data.ssh_proxy, proxy_identity))

            for attempt in range(retries):
                last = attempt == retries - 1
                # remote_host:local mapping
                tunnel_ports_map = _reserve_ports(container_ports_map.values())
                runner_ports_map = {
                    container_port: tunnel_ports_map[host_port]
                    for container_port, host_port in container_ports_map.items()
                }
                try:
                    with SSHTunnel(
                        destination=(
                            f"{job_provisioning_data.username}@{job_provisioning_data.hostname}"
                        ),
                        port=job_provisioning_data.ssh_port,
                        forwarded_sockets=ports_to_forwarded_sockets(tunnel_ports_map),
                        identity=identity,
                        ssh_proxies=ssh_proxies,
                    ):
                        return func(runner_ports_map, *args, **kwargs)
                except SSHError:
                    pass  # error is logged in the tunnel
                except (DstackError, requests.RequestException) as e:
                    if last:
                        logger.debug(
                            "Cannot connect to %s's API: %s", job_provisioning_data.hostname, e
                        )
                if not last:
                    time.sleep(retry_interval)
            return False

        return wrapper

    return decorator


def _reserve_ports(ports: Iterable[int]) -> dict[int, int]:
    sockets = []
    try:
        for port in ports:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("localhost", 0))  # Bind to a free port provided by the host
            sockets.append((port, s))
        return {port: s.getsockname()[1] for port, s in sockets}
    finally:
        for _, s in sockets:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.close()
