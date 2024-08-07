import contextlib
import os
import uuid
from typing import AsyncIterator, Dict, Optional

import aiorwlock

from dstack._internal.server.services.gateways.client import (
    GATEWAY_MANAGEMENT_PORT,
    GatewayClient,
    Stat,
)
from dstack._internal.server.services.ssh import AsyncSSHTunnel
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


SERVER_PORT_ON_GATEWAY = 8001


class GatewayConnection:
    """
    `GatewayConnection` instances persist for the lifetime of the gateway.

    The `GatewayConnection.tunnel` is responsible for establishing a bidirectional tunnel with the gateway.
    The local tunnel is used for the gateway management.
    The reverse tunnel is used for authorizing dstack tokens.
    """

    def __init__(self, ip_address: str, id_rsa: str, server_port: int):
        self._lock = aiorwlock.RWLock()
        self.stats: Dict[str, Dict[int, Stat]] = {}
        self.ip_address = ip_address
        args = ["-L", "{temp_dir}/gateway:localhost:%d" % GATEWAY_MANAGEMENT_PORT]
        args += ["-R", f"localhost:{SERVER_PORT_ON_GATEWAY}:localhost:{server_port}"]
        self.tunnel = AsyncSSHTunnel(
            f"ubuntu@{ip_address}",
            id_rsa,
            {
                "StrictHostKeyChecking": "no",
                "UserKnownHostsFile": "/dev/null",
                "ExitOnForwardFailure": "yes",
                "StreamLocalBindUnlink": "yes",
                "ConnectTimeout": 1,
                "ServerAliveInterval": 60,
            },
            args,
        )
        self._client = GatewayClient(uds=os.path.join(self.tunnel.temp_dir, "gateway"))

    async def check_or_restart(self):
        async with self._lock.writer_lock:
            if not await self.tunnel.check():
                logger.info("Connection to gateway %s is down, restarting", self.ip_address)
                await self.tunnel.start()
        return

    async def try_collect_stats(self) -> None:
        if not self._client.is_server_ready:
            return

        async with self._lock.writer_lock:
            self.stats = await self._client.collect_stats()
            for service_id, stats in self.stats.items():
                logger.debug("%s stats: %s", service_id, stats)

    async def get_stats(self, service_id: uuid.UUID) -> Optional[Dict[int, Stat]]:
        async with self._lock.reader_lock:
            return self.stats.get(service_id.hex)

    @contextlib.asynccontextmanager
    async def client(self) -> AsyncIterator[GatewayClient]:
        async with self._lock.reader_lock:
            yield self._client
