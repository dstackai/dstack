import asyncio
import socket
from contextlib import closing
from typing import Dict, Hashable

from dstack._internal.core.errors import SSHError
from dstack._internal.core.services.ssh.tunnel import SSHTunnel
from dstack._internal.server.utils.common import run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class RunnerConnectionPool:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._ports: Dict[Hashable, int] = {}
        self._tunnels: Dict[int, SSHTunnel] = {}

    async def connect(self, key: Hashable, hostname: str, id_rsa: bytes) -> int:
        """
        :return: local port forwarded to port 10999 on the remote host
        """
        async with self._lock:
            if key in self._ports:
                return self._ports[key]
            self._ports[key] = port = await run_async(self._allocate_port)

        self._tunnels[port] = tunnel = SSHTunnel(
            hostname=hostname,
            ports={10999: port},
            id_rsa=id_rsa,
        )
        try:
            logger.info(f"Opening SSH connection to {hostname} through port {port}")
            await run_async(tunnel.open)
        except SSHError:
            self._tunnels.pop(port)
            async with self._lock:
                self._ports.pop(key)
            raise
        return port

    async def disconnect(self, key: Hashable):
        async with self._lock:
            port = self._ports.pop(key)  # raises KeyError if not found
        tunnel = self._tunnels.pop(port)
        logger.info(f"Closing SSH connection to {tunnel.host}")
        await run_async(tunnel.close)

    def _allocate_port(self) -> int:
        while True:
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
                s.bind(("", 0))
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                port = s.getsockname()[1]
            if port not in self._tunnels:
                return port
