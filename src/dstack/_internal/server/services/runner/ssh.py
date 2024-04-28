import functools
import inspect
import socket
import time
from typing import Callable, Dict, List, Optional

import requests
from typing_extensions import Concatenate, ParamSpec

from dstack._internal.core.errors import SSHError
from dstack._internal.core.models.runs import JobProvisioningData
from dstack._internal.core.services.ssh.tunnel import RunnerTunnel
from dstack._internal.server.services.runner import client
from dstack._internal.server.settings import LOCAL_BACKEND_ENABLED
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)
P = ParamSpec("P")


def runner_ssh_tunnel(
    ports: List[int], retries: int = 3, retry_interval: float = 1
) -> Callable[[Callable[P, bool]], Callable[Concatenate[str, JobProvisioningData, P], bool]]:
    def decorator(
        func: Callable[P, bool],
    ) -> Callable[Concatenate[str, JobProvisioningData, P], bool]:
        @functools.wraps(func)
        def wrapper(
            ssh_private_key: str,
            job_provisioning_data: JobProvisioningData,
            *args: P.args,
            **kwargs: P.kwargs,
        ) -> bool:
            """
            Returns:
                is successful
            """

            if LOCAL_BACKEND_ENABLED:
                # without SSH
                port_map = {p: p for p in ports}
                return func(*args, ports=port_map, **kwargs)

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
                try:
                    with RunnerTunnel(
                        hostname=job_provisioning_data.hostname,
                        ssh_port=job_provisioning_data.ssh_port,
                        user=job_provisioning_data.username,
                        ports=get_runner_ports(ports=ports),
                        id_rsa=ssh_private_key,
                        ssh_proxy=job_provisioning_data.ssh_proxy,
                    ) as tun:
                        return func(*args, ports=tun.ports, **ssh_kwargs, **kwargs)
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
