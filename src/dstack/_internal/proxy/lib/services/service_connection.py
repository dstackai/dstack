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
from dstack._internal.utils.common import get_or_error
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import FileContent

logger = get_logger(__name__)
OPEN_TUNNEL_TIMEOUT = 10
# Bound SSH startup work during a shared outage, without limiting service requests.
MAX_CONCURRENT_TUNNEL_RECONNECTS = 8
MAX_TUNNEL_RECONNECT_DELAY = 30


class ServiceClient(httpx.AsyncClient):
    def build_request(self, *args, **kwargs) -> httpx.Request:
        self.cookies.clear()  # the client is shared by all users, don't leak cookies
        return super().build_request(*args, **kwargs)


class ServiceConnection:
    """Forward a replica's HTTP traffic over SSH to a stable local Unix socket.

    Gateways supervise and reconnect the SSH process so Nginx can keep
    using the same socket path. The in-server proxy opens connections on demand.
    """

    def __init__(
        self,
        project: Project,
        service: Service,
        replica: Replica,
        reconnect_semaphore: asyncio.Semaphore,
    ) -> None:
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
            background=service.domain is None,
        )
        self._client = ServiceClient(
            transport=AsyncHTTPTransport(uds=str(self._app_socket_path)),
            # The hostname in base_url is there for troubleshooting, as it may appear in
            # logs and in the Host header. The actual destination is the Unix socket.
            base_url=f"http://{replica.id}-{service.run_name}/",
            timeout=service.read_timeout,
        )
        self._is_open = asyncio.locks.Event()
        self._lifecycle_lock = asyncio.Lock()
        self._closed = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._auto_reconnect = service.domain is not None
        self._replica_id = replica.id
        self._reconnect_semaphore = reconnect_semaphore

    @property
    def app_socket_path(self) -> Path:
        return self._app_socket_path

    async def open(self) -> None:
        async with self._lifecycle_lock:
            if self._closed:
                raise UnexpectedProxyError("Cannot open a closed service connection")
            if self._is_open.is_set():
                return
            await self._tunnel.aopen()
            if self._closed:
                # Removal may have started while SSH was connecting.
                raise UnexpectedProxyError("Service connection was removed while opening")
            self._is_open.set()
            if self._auto_reconnect:
                self._monitor_task = asyncio.create_task(self._monitor_tunnel())

    async def close(self) -> None:
        self._closed = True
        # Removal must finish cleaning up even if its caller is cancelled.
        cleanup = asyncio.create_task(self._close())
        cancelled = None
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError as e:
                cancelled = e
        cleanup.result()
        if cancelled is not None:
            raise cancelled

    async def client(self) -> ServiceClient:
        await asyncio.wait_for(self._is_open.wait(), timeout=OPEN_TUNNEL_TIMEOUT)
        return self._client

    async def _close(self) -> None:
        async with self._lifecycle_lock:
            if self._monitor_task is not None:
                self._monitor_task.cancel()
                await asyncio.gather(self._monitor_task, return_exceptions=True)
                self._monitor_task = None
            self._is_open.clear()
            try:
                await self._client.aclose()
            finally:
                await self._tunnel.aclose()

    async def _monitor_tunnel(self) -> None:
        loop = asyncio.get_running_loop()
        retry_delay = 0
        while True:
            started_at = loop.time()
            await self._tunnel.wait_closed()
            if loop.time() - started_at >= MAX_TUNNEL_RECONNECT_DELAY:
                retry_delay = 0
            logger.warning("SSH tunnel to replica %s exited, reconnecting", self._replica_id)
            # Reap any surviving ProxyCommand children before opening a replacement.
            await self._tunnel.aclose()
            while True:
                if retry_delay:
                    await asyncio.sleep(random.uniform(retry_delay / 2, retry_delay))
                # Back off failed starts and tunnels that repeatedly exit just after startup.
                retry_delay = min(max(1, retry_delay * 2), MAX_TUNNEL_RECONNECT_DELAY)
                try:
                    async with self._reconnect_semaphore:
                        # Keep the socket path configured in Nginx. SSH replaces stale sockets.
                        await self._tunnel.aopen()
                except Exception as e:
                    logger.warning("Could not reconnect to replica %s: %s", self._replica_id, e)
                else:
                    logger.info("SSH tunnel to replica %s reconnected", self._replica_id)
                    break


class ServiceConnectionPool:
    def __init__(self) -> None:
        # TODO(#2238): remove connections to stopped replicas in-server
        self.connections: Dict[str, ServiceConnection] = {}
        self._reconnect_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TUNNEL_RECONNECTS)

    async def get(self, replica_id: str) -> Optional[ServiceConnection]:
        return self.connections.get(replica_id)

    async def get_or_add(
        self, project: Project, service: Service, replica: Replica
    ) -> ServiceConnection:
        connection = self.connections.get(replica.id)
        if connection is not None:
            return connection
        connection = ServiceConnection(project, service, replica, self._reconnect_semaphore)
        self.connections[replica.id] = connection
        try:
            await connection.open()
        except BaseException:
            if self.connections.get(replica.id) is connection:
                self.connections.pop(replica.id)
            try:
                await connection.close()
            except Exception:
                logger.exception("Error closing failed connection to replica %s", replica.id)
            raise
        return connection

    async def remove(self, replica_id: str) -> None:
        connection = self.connections.pop(replica_id, None)
        if connection is not None:
            await connection.close()

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
