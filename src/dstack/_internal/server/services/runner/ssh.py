import functools
import time
from typing import Callable, List

import requests
from typing_extensions import Concatenate, ParamSpec

from dstack._internal.core.errors import SSHError
from dstack._internal.core.models.runs import JobProvisioningData
from dstack._internal.core.services.ssh.tunnel import RunnerTunnel
from dstack._internal.server.services.jobs import get_runner_ports
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)
P = ParamSpec("P")


def runner_ssh_tunnel(
    ports: List[int], retries: int = 3, retry_interval: float = 1
) -> Callable[[Callable[P, bool]], Callable[Concatenate[str, JobProvisioningData, P], bool]]:
    def decorator(
        func: Callable[P, bool]
    ) -> Callable[Concatenate[str, JobProvisioningData, P], bool]:
        @functools.wraps(func)
        def wrapper(
            ssh_private_key: str,
            job_provisioning_data: JobProvisioningData,
            *args: P.args,
            **kwargs: P.kwargs
        ) -> bool:
            """
            Returns:
                is successful
            """
            for attempt in range(retries):
                last = attempt == retries - 1
                try:
                    with RunnerTunnel(
                        hostname=job_provisioning_data.hostname,
                        ssh_port=job_provisioning_data.ssh_port,
                        user=job_provisioning_data.username,
                        ports=get_runner_ports(ports=ports),
                        id_rsa=ssh_private_key,
                    ) as tun:
                        return func(*args, ports=tun.ports, **kwargs)
                except SSHError as e:
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
