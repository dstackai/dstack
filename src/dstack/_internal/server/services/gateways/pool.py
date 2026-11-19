import asyncio
from weakref import WeakValueDictionary

from dstack._internal.server.services.gateways.connection import GatewayConnection, ssh_key_digest
from dstack._internal.server.settings import SERVER_PORT


class GatewayConnectionsPool:
    def __init__(self) -> None:
        self._connections: dict[str, tuple[str, GatewayConnection]] = {}
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

    async def get_or_add(
        self,
        hostname: str,
        id_rsa: str,
        close_existing_tunnel: bool = False,
    ) -> GatewayConnection:
        digest = ssh_key_digest(id_rsa)
        async with self._locks.setdefault(hostname, asyncio.Lock()):
            cached = self._connections.get(hostname)
            if cached is not None:
                cached_digest, connection = cached
                if cached_digest == digest:
                    return connection
                del self._connections[hostname]
                await connection.close()
            connection = GatewayConnection(hostname, id_rsa, SERVER_PORT)
            try:
                await connection.open(close_existing_tunnel=close_existing_tunnel)
            except (Exception, asyncio.CancelledError):
                await connection.close()
                raise
            self._connections[hostname] = (digest, connection)
            return connection

    async def remove(self, hostname: str) -> bool:
        async with self._locks.setdefault(hostname, asyncio.Lock()):
            cached = self._connections.pop(hostname, None)
            if cached is None:
                return False
            _, connection = cached
            await connection.close()
            return True

    async def remove_all(self) -> None:
        # Include hosts still opening, before their connections have been published.
        hosts = set(self._connections).union(self._locks)
        await asyncio.gather(*(self.remove(host) for host in hosts), return_exceptions=True)

    async def all(self) -> list[GatewayConnection]:
        return [connection for _, connection in self._connections.values()]


gateway_connections_pool: GatewayConnectionsPool = GatewayConnectionsPool()
