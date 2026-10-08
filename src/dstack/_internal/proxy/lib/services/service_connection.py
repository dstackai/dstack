import asyncio
import os
import random
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, Optional

import httpx
from httpx import AsyncHTTPTransport

from dstack._internal.core.services.ssh.tunnel import (
    SSH_DEFAULT_OPTIONS,
    IPSocket,
    SocketPair,
    SSHTunnel,
    UnixSocket,
)
from dstack._internal.proxy.lib.errors import UnexpectedProxyError
from dstack._internal.proxy.lib.models import Project, Replica, Service
from dstack._internal.proxy.lib.repo import BaseProxyRepo
from dstack._internal.utils.common import get_or_error, run_async
from dstack._internal.utils.env import environ
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import FileContent

logger = get_logger(__name__)
OPEN_TUNNEL_TIMEOUT = 10
TUNNEL_CHECK_INTERVAL = environ.get_int("DSTACK_PROXY_TUNNEL_CHECK_INTERVAL", default=15)
"""Seconds between checks that reopen replica SSH tunnels whose ssh process has exited."""


class ServiceClient(httpx.AsyncClient):
    def build_request(self, *args, **kwargs) -> httpx.Request:
        self.cookies.clear()  # the client is shared by all users, don't leak cookies
        return super().build_request(*args, **kwargs)


class ServiceConnection:
    def __init__(self, project: Project, service: Service, replica: Replica) -> None:
        self._temp_dir = TemporaryDirectory()
        options = {
            **SSH_DEFAULT_OPTIONS,
            "ConnectTimeout": str(OPEN_TUNNEL_TIMEOUT),
            "ServerAliveInterval": "60",
        }
        if service.domain is not None:
            # expose socket for Nginx
            os.chmod(self._temp_dir.name, 0o755)
            options["StreamLocalBindMask"] = "0111"
        self._app_socket_path = (Path(self._temp_dir.name) / "replica.sock").absolute()
        ssh_proxies = []
        if replica.ssh_head_proxy is not None:
            ssh_head_proxy_private_key = get_or_error(replica.ssh_head_proxy_private_key)
            ssh_proxies.append((replica.ssh_head_proxy, FileContent(ssh_head_proxy_private_key)))
        if replica.ssh_proxy is not None:
            if replica.ssh_proxy_private_key is not None:
                ssh_proxies.append((replica.ssh_proxy, FileContent(replica.ssh_proxy_private_key)))
            else:
                ssh_proxies.append((replica.ssh_proxy, None))
        self._tunnel = SSHTunnel(
            destination=replica.ssh_destination,
            port=replica.ssh_port,
            ssh_proxies=ssh_proxies,
            identity=FileContent(project.ssh_private_key),
            forwarded_sockets=[
                SocketPair(
                    remote=IPSocket("localhost", replica.app_port),
                    local=UnixSocket(self._app_socket_path),
                ),
            ],
            options=options,
        )
        self._client = ServiceClient(
            transport=AsyncHTTPTransport(uds=str(self._app_socket_path)),
            # The hostname in base_url is there for troubleshooting, as it may appear in
            # logs and in the Host header. The actual destination is the Unix socket.
            base_url=f"http://{replica.id}-{service.run_name}/",
            timeout=service.read_timeout,
        )
        self._is_open = asyncio.locks.Event()
        self._replica_id = replica.id
        self._lock = asyncio.Lock()
        self._closed = False

    @property
    def app_socket_path(self) -> Path:
        return self._app_socket_path

    async def open(self) -> None:
        await self._tunnel.aopen()
        self._is_open.set()

    async def close(self) -> None:
        async with self._lock:
            self._closed = True
            self._is_open.clear()
            await self._client.aclose()
            await self._tunnel.aclose()

    async def reopen_if_exited(self) -> bool:
        """
        Reopen the SSH tunnel if its ssh process has exited, e.g. after the replica's SSH server
        dropped the connection because the gateway missed keepalives. The local app socket path
        is kept, so nginx and the HTTP client keep working without reconfiguration.

        Returns `True` if the tunnel was reopened.
        """
        if self._closed or not self._is_open.is_set():
            return False
        if await self._tunnel.acheck():
            return False
        async with self._lock:
            if self._closed or await self._tunnel.acheck():
                return False
            logger.warning("SSH tunnel to service replica %s exited, reopening", self._replica_id)
            # The control socket of a killed ssh process stays on disk. A new ssh with
            # `ControlMaster=auto` would then run without a control socket and fail every check.
            await run_async(_remove_file, Path(self._tunnel.control_sock_path))
            await self._tunnel.aopen()
        return True

    async def client(self) -> ServiceClient:
        await asyncio.wait_for(self._is_open.wait(), timeout=OPEN_TUNNEL_TIMEOUT)
        return self._client


class ServiceConnectionPool:
    def __init__(self) -> None:
        # TODO(#2238): remove connections to stopped replicas in-server
        self.connections: Dict[str, ServiceConnection] = {}

    async def get(self, replica_id: str) -> Optional[ServiceConnection]:
        return self.connections.get(replica_id)

    async def get_or_add(
        self, project: Project, service: Service, replica: Replica
    ) -> ServiceConnection:
        connection = self.connections.get(replica.id)
        if connection is not None:
            return connection
        connection = ServiceConnection(project, service, replica)
        self.connections[replica.id] = connection
        try:
            await connection.open()
        except BaseException:
            self.connections.pop(replica.id, None)
            raise
        return connection

    async def remove(self, replica_id: str) -> None:
        connection = self.connections.pop(replica_id, None)
        if connection is not None:
            await connection.close()

    async def reopen_exited(self) -> None:
        connections = list(self.connections.items())
        results = await asyncio.gather(
            *(connection.reopen_if_exited() for _, connection in connections),
            return_exceptions=True,
        )
        for (replica_id, _), result in zip(connections, results):
            if isinstance(result, BaseException):
                logger.warning(
                    "Failed to reopen SSH tunnel to service replica %s: %r", replica_id, result
                )
            elif result:
                logger.info("Reopened SSH tunnel to service replica %s", replica_id)

    async def remove_all(self) -> None:
        replica_ids = list(self.connections)
        results = await asyncio.gather(
            *(self.remove(replica_id) for replica_id in replica_ids), return_exceptions=True
        )
        for i, exc in enumerate(results):
            if isinstance(exc, Exception):
                logger.error(
                    "Error removing connection to service replica %s: %s", replica_ids[i], exc
                )


async def get_service_replica_client(
    service: Service, repo: BaseProxyRepo, service_conn_pool: ServiceConnectionPool
) -> httpx.AsyncClient:
    """
    `service` must have at least one replica
    """
    if service.domain is not None:
        # Forward to Nginx so that requests are visible to StatsCollector in the access log
        return httpx.AsyncClient(
            base_url="http://127.0.0.1",
            headers={"Host": service.domain},
            timeout=service.read_timeout,
        )
    # Nginx not available, forward directly to the tunnel
    replica = random.choice(service.replicas)
    connection = await service_conn_pool.get(replica.id)
    if connection is None:
        project = await repo.get_project(service.project_name)
        if project is None:
            raise UnexpectedProxyError(
                f"Expected to find project {service.project_name} but could not"
            )
        connection = await service_conn_pool.get_or_add(project, service, replica)
    return await connection.client()


async def maintain_service_connections(
    service_conn_pool: ServiceConnectionPool, interval: float = TUNNEL_CHECK_INTERVAL
) -> None:
    """Periodically reopen replica SSH tunnels whose ssh process has exited."""
    while True:
        await asyncio.sleep(interval)
        try:
            await service_conn_pool.reopen_exited()
        except Exception:
            logger.exception("Failed to check service replica SSH tunnels")


def _remove_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
