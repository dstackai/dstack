import functools
import inspect
import socket
import time
from typing import Callable, Dict, List, Optional, TypeVar, Union

import requests
from typing_extensions import Concatenate, ParamSpec

from dstack._internal.core.errors import SSHError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.runs import JobProvisioningData
from dstack._internal.core.services.ssh.tunnel import SSHTunnel, ports_to_forwarded_sockets
from dstack._internal.server.services.runner import client
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import FileContent

logger = get_logger(__name__)
P = ParamSpec("P")
R = TypeVar("R")


def runner_ssh_tunnel(
    ports: List[int], retries: int = 3, retry_interval: float = 1
) -> Callable[
    [Callable[Concatenate[Dict[int, int], P], R]],
    Callable[Concatenate[str, JobProvisioningData, P], Union[bool, R]],
]:
    def decorator(
        func: Callable[Concatenate[Dict[int, int], P], R],
    ) -> Callable[Concatenate[str, JobProvisioningData, P], Union[bool, R]]:
        @functools.wraps(func)
        def wrapper(
            ssh_private_key: str,
            job_provisioning_data: JobProvisioningData,
            *args: P.args,
            **kwargs: P.kwargs,
        ) -> Union[bool, R]:
            """
            Returns:
                is successful
            """

            if job_provisioning_data.backend == BackendType.LOCAL:
                # without SSH
                port_map = {p: p for p in ports}
                return func(port_map, *args, **kwargs)

            func_kwargs_names = [
                p.name
                for p in inspect.signature(func).parameters.values()
                if p.kind == p.KEYWORD_ONLY
            ]
            ssh_kwargs = {}
            if "ssh_private_key" in func_kwargs_names:
                ssh_kwargs["ssh_private_key"] = ssh_private_key
            if "job_provisioning_data" in func_kwargs_names:
                ssh_kwargs["job_provisioning_data"] = job_provisioning_data

            for attempt in range(retries):
                last = attempt == retries - 1
                runner_ports_map = get_runner_ports(ports=ports)
                try:
                    with SSHTunnel(
                        destination=(
                            f"{job_provisioning_data.username}@{job_provisioning_data.hostname}"
                        ),
                        port=job_provisioning_data.ssh_port,
                        forwarded_sockets=ports_to_forwarded_sockets(runner_ports_map),
                        identity=FileContent(ssh_private_key),
                        ssh_proxy=job_provisioning_data.ssh_proxy,
                    ):
                        return func(runner_ports_map, *args, **ssh_kwargs, **kwargs)
                except SSHError:
                    pass  # error is logged in the tunnel
                except requests.RequestException as e:
                    if last:
                        logger.debug(
                            "Cannot connect to %s's API: %s", job_provisioning_data.hostname, e
                        )
                if not last:
                    time.sleep(retry_interval)
            return False

        return wrapper

    return decorator


def get_runner_ports(ports: Optional[List[int]] = None) -> Dict[int, int]:
    ports = ports or [client.REMOTE_RUNNER_PORT]
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
