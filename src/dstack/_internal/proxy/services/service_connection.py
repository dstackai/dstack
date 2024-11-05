import asyncio
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
from dstack._internal.proxy.errors import UnexpectedProxyError
from dstack._internal.proxy.repos.base import BaseProxyRepo, Project, Replica, Service
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import FileContent

logger = get_logger(__name__)
OPEN_TUNNEL_TIMEOUT = 10


class ServiceReplicaClient(httpx.AsyncClient):
    def build_request(self, *args, **kwargs) -> httpx.Request:
        self.cookies.clear()  # the client is shared by all users, don't leak cookies
        return super().build_request(*args, **kwargs)


class ServiceReplicaConnection:
    def __init__(self, project: Project, service: Service, replica: Replica) -> None:
        self._temp_dir = TemporaryDirectory()
        app_socket_path = (Path(self._temp_dir.name) / "replica.sock").absolute()
        self._tunnel = SSHTunnel(
            destination=replica.ssh_destination,
            port=replica.ssh_port,
            ssh_proxy=replica.ssh_proxy,
            identity=FileContent(project.ssh_private_key),
            forwarded_sockets=[
                SocketPair(
                    remote=IPSocket("localhost", service.app_port),
                    local=UnixSocket(app_socket_path),
                ),
            ],
            options={
                **SSH_DEFAULT_OPTIONS,
                "ConnectTimeout": str(OPEN_TUNNEL_TIMEOUT),
            },
        )
        self._client = ServiceReplicaClient(
            transport=AsyncHTTPTransport(uds=str(app_socket_path)),
            # The hostname in base_url is there for troubleshooting, as it may appear in
            # logs and in the Host header. The actual destination is the Unix socket.
            base_url=f"http://{replica.id}-{service.run_name}/",
            timeout=60,  # Same as default Nginx proxy timeout
        )
        self._is_open = asyncio.locks.Event()

    async def open(self) -> None:
        await self._tunnel.aopen()
        self._is_open.set()

    async def close(self) -> None:
        self._is_open.clear()
        await self._client.aclose()
        await self._tunnel.aclose()

    async def client(self) -> ServiceReplicaClient:
        await asyncio.wait_for(self._is_open.wait(), timeout=OPEN_TUNNEL_TIMEOUT)
        return self._client


class ServiceReplicaConnectionPool:
    def __init__(self) -> None:
        # TODO(#1595): remove connections to stopped replicas
        self.connections: Dict[str, ServiceReplicaConnection] = {}

    async def get(self, replica_id: str) -> Optional[ServiceReplicaConnection]:
        return self.connections.get(replica_id)

    async def add(
        self, project: Project, service: Service, replica: Replica
    ) -> ServiceReplicaConnection:
        connection = self.connections.get(replica.id)
        if connection is not None:
            return connection
        connection = ServiceReplicaConnection(project, service, replica)
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
    project_name: str, service: Service, repo: BaseProxyRepo
) -> ServiceReplicaClient:
    """
    `service` must have at least one replica
    """
    # TODO(#1595): consider trying different replicas if the first one doesn't respond
    replica = random.choice(service.replicas)
    connection = await service_replica_connection_pool.get(replica.id)
    if connection is None:
        project = await repo.get_project(project_name)
        if project is None:
            raise UnexpectedProxyError(f"Expected to find project {project_name} but could not")
        connection = await service_replica_connection_pool.add(project, service, replica)
    return await connection.client()


service_replica_connection_pool: ServiceReplicaConnectionPool = ServiceReplicaConnectionPool()
