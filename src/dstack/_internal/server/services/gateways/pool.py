import asyncio
from typing import Dict, List

from dstack._internal.server.services.gateways.connection import GatewayConnection
from dstack._internal.server.settings import SERVER_PORT
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class GatewayConnectionsPool:
    def __init__(self) -> None:
        self._connections: Dict[str, GatewayConnection] = {}
        self._lock = asyncio.Lock()

    async def get_or_add(
        self,
        hostname: str,
        id_rsa: str,
        close_existing_tunnel: bool = False,
    ) -> GatewayConnection:
        async with self._lock:
            connection = self._connections.get(hostname)
            if connection is not None:
                return connection
            self._connections[hostname] = GatewayConnection(hostname, id_rsa, SERVER_PORT)
            open_task = self._connections[hostname].open(
                close_existing_tunnel=close_existing_tunnel,
            )
        try:
            await open_task
            return self._connections[hostname]
        except Exception:
            async with self._lock:
                self._connections.pop(hostname, None)
            raise

    async def remove(self, hostname: str) -> bool:
        async with self._lock:
            if hostname not in self._connections:
                return False
            close_task = self._connections.pop(hostname).close()
        await close_task
        return True

    async def remove_all(self) -> None:
        async with self._lock:
            await asyncio.gather(
                *(conn.close() for conn in self._connections.values()),
                return_exceptions=True,
            )
            self._connections = {}

    async def all(self) -> List[GatewayConnection]:
        return list(self._connections.values())


gateway_connections_pool: GatewayConnectionsPool = GatewayConnectionsPool()
