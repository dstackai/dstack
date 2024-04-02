import asyncio
from typing import Dict, List, Optional

from dstack._internal.server.services.gateways.connection import GatewayConnection
from dstack._internal.server.settings import SERVER_PORT
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class GatewayConnectionsPool:
    def __init__(self) -> None:
        self._connections: Dict[str, GatewayConnection] = {}
        self._lock = asyncio.Lock()

    async def add(self, hostname: str, id_rsa: str) -> GatewayConnection:
        async with self._lock:
            if hostname in self._connections:
                logger.warning(f"Gateway connection for {hostname} already exists")
                return self._connections[hostname]
            self._connections[hostname] = GatewayConnection(hostname, id_rsa, SERVER_PORT)
            start_task = self._connections[hostname].tunnel.start()
        try:
            await start_task
            return self._connections[hostname]
        except Exception:
            async with self._lock:
                self._connections.pop(hostname, None)
            raise

    async def remove(self, hostname: str) -> bool:
        async with self._lock:
            if hostname not in self._connections:
                logger.warning(f"Gateway connection for {hostname} does not exist")
                return False
            stop_task = self._connections.pop(hostname).tunnel.stop()
        await stop_task
        return True

    async def remove_all(self) -> None:
        async with self._lock:
            await asyncio.gather(
                *(conn.tunnel.stop() for conn in self._connections.values()),
                return_exceptions=True,
            )
            self._connections = {}

    async def get(self, hostname: str) -> Optional[GatewayConnection]:
        return self._connections.get(hostname)

    async def all(self) -> List[GatewayConnection]:
        return list(self._connections.values())


gateway_connections_pool: GatewayConnectionsPool = GatewayConnectionsPool()
