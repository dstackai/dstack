import functools
from typing import Callable, Dict, List, Literal, Optional, TypeVar, Union

import requests
from typing_extensions import Concatenate, ParamSpec

from dstack._internal.core.errors import DstackError, SSHError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.runs import JobProvisioningData, JobRuntimeData
from dstack._internal.server.services.runner.pool import instance_connection_pool
from dstack._internal.utils.logging import get_logger

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
        Union[Literal[False], R],
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
        Union[Literal[False], R],
    ]:
        @functools.wraps(func)
        def wrapper(
            ssh_private_key: PrivateKeyOrPair,
            jpd: JobProvisioningData,
            jrd: Optional[JobRuntimeData],
            *args: P.args,
            **kwargs: P.kwargs,
        ) -> Union[Literal[False], R]:
            """
            Returns:
                is successful
            """
            if jpd.backend == BackendType.LOCAL:
                # without SSH
                container_ports_map = {port: port for port in ports}
                return func(container_ports_map, *args, **kwargs)

            for attempt in range(2):  # cached, then one fresh reopen
                conn = instance_connection_pool.get_or_open(ssh_private_key, jpd, jrd)
                if conn is None:
                    return False  # couldn't establish at all
                sock_paths = {p: conn.forwarded_path(p) for p in ports}
                try:
                    return func(sock_paths, *args, **kwargs)
                except (SSHError, requests.ConnectionError):
                    instance_connection_pool.drop(conn.key)  # dead ssh connection, re-open
                except (DstackError, requests.RequestException):
                    return False  # reached runner, app-level fail; don't re-open ssh connection
            return False

        return wrapper

    return decorator
