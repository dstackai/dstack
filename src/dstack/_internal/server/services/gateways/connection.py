import contextlib
import shutil
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import AsyncIterator, Dict, Optional, Tuple

import aiorwlock

from dstack._internal.core.services.ssh.tunnel import (
    SSH_DEFAULT_OPTIONS,
    IPSocket,
    SocketPair,
    SSHTunnel,
    UnixSocket,
)
from dstack._internal.server.services.gateways.client import (
    GATEWAY_MANAGEMENT_PORT,
    GatewayClient,
    Stat,
)
from dstack._internal.server.settings import SERVER_DIR_PATH
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import FileContent

logger = get_logger(__name__)
CONNECTIONS_DIR = SERVER_DIR_PATH / "gateway-connections"
CONNECTIONS_DIR_ON_GATEWAY = "/home/ubuntu/dstack/server-connections"


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
        self.server_port = server_port
        # a persistent connection_dir is needed to discover and close leftover connections
        # in case of server restarts w/o graceful shutdown
        self.connection_dir = CONNECTIONS_DIR / ip_address
        # connection_dir can have a long path that won't be accepted by the ssh command,
        # so we create a short temporary symlink
        self.temp_dir, self.connection_symlink_dir = self._init_symlink_dir(self.connection_dir)
        self.gateway_socket_path = self.connection_symlink_dir / "gateway.sock"
        self.tunnel = SSHTunnel(
            destination=f"ubuntu@{ip_address}",
            identity=FileContent(id_rsa),
            control_sock_path=self.connection_symlink_dir / "control.sock",
            options={
                **SSH_DEFAULT_OPTIONS,
                "ConnectTimeout": "1",
                "ServerAliveInterval": "60",
            },
            forwarded_sockets=[
                SocketPair(
                    local=UnixSocket(path=self.gateway_socket_path),
                    remote=IPSocket(host="localhost", port=GATEWAY_MANAGEMENT_PORT),
                ),
            ],
            # reverse_forwarded_sockets are added later in .open()
        )
        self.tunnel_id = uuid.uuid4()
        self._client = GatewayClient(uds=self.gateway_socket_path)

    @staticmethod
    def _init_symlink_dir(connection_dir: Path) -> Tuple[TemporaryDirectory, Path]:
        temp_dir = TemporaryDirectory()
        symlink_dir = Path(temp_dir.name) / "connection"
        symlink_dir.symlink_to(connection_dir, target_is_directory=True)
        return temp_dir, symlink_dir

    async def check_or_restart(self) -> bool:
        async with self._lock.writer_lock:
            if not await self.tunnel.acheck():
                logger.info("Connection to gateway %s is down, restarting", self.ip_address)
                await self._open_tunnel()
                return True
        return False

    async def open(self, close_existing_tunnel: bool = False) -> None:
        async with self._lock.writer_lock:
            if close_existing_tunnel:
                # Close remaining tunnel if previous server process died w/o graceful shutdown
                if await self.tunnel.acheck():
                    await self.tunnel.aclose()
            await self._open_tunnel()

    async def _open_tunnel(self) -> None:
        self.connection_dir.mkdir(parents=True, exist_ok=True)
        remote_socket_path = f"{CONNECTIONS_DIR_ON_GATEWAY}/{self.tunnel_id}.sock"

        # open w/o reverse forwarding and make sure reverse forwarding will be possible
        self.tunnel.reverse_forwarded_sockets = []
        await self.tunnel.aopen()
        await self.tunnel.aexec(f"mkdir -p {CONNECTIONS_DIR_ON_GATEWAY}")
        await self.tunnel.aexec(f"rm -f {remote_socket_path}")

        # add reverse forwarding
        self.tunnel.reverse_forwarded_sockets = [
            SocketPair(
                local=IPSocket(host="localhost", port=self.server_port),
                remote=UnixSocket(path=remote_socket_path),
            ),
        ]
        await self.tunnel.aopen()

    async def close(self) -> None:
        async with self._lock.writer_lock:
            await self.tunnel.aclose()
            shutil.rmtree(self.connection_dir, ignore_errors=True)

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
