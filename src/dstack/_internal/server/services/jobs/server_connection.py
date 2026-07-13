import asyncio
import shlex
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional
from weakref import WeakValueDictionary

import httpx

from dstack._internal.core.consts import DSTACK_RUN_SERVER_SOCKET_PATH
from dstack._internal.core.errors import SSHError
from dstack._internal.core.models.runs import JobRuntimeData
from dstack._internal.core.services.ssh.tunnel import (
    SSH_DEFAULT_OPTIONS,
    IPSocket,
    SocketPair,
    SSHTunnel,
    UnixSocket,
)
from dstack._internal.server import settings
from dstack._internal.server.models import JobModel
from dstack._internal.server.services.ssh import get_container_ssh_credentials
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import make_tmp_symlink_to_dir

logger = get_logger(__name__)

CONNECTIONS_DIR = settings.SERVER_DIR_PATH / "job-server-connections"
_MIN_ALIVE_CHECK_INTERVAL = 30
_PROBE_TIMEOUT = 3
_REMOTE_SOCKET_PATH = Path(DSTACK_RUN_SERVER_SOCKET_PATH)


def _get_server_socket() -> IPSocket:
    # The server may be bound to a specific address, making loopback unreachable
    host = settings.SERVER_HOST
    if not host or host in ("0.0.0.0", "localhost"):
        host = "127.0.0.1"
    elif host == "::":
        host = "::1"
    return IPSocket(host=host, port=settings.SERVER_PORT)


class JobServerConnection:
    """A private reverse SSH tunnel from one job to the dstack server."""

    def __init__(self, job: JobModel, job_runtime_data: Optional[JobRuntimeData]) -> None:
        self.job_id = job.id
        self._last_verified_at = 0.0
        # Keep the control socket discoverable across server process restarts. The temporary
        # symlink keeps its effective path below OpenSSH's Unix-socket length limit.
        self._connection_dir = CONNECTIONS_DIR / str(job.id)
        self._connection_dir.mkdir(parents=True, exist_ok=True)
        self._temp_dir, effective_dir = make_tmp_symlink_to_dir(
            self._connection_dir,
            "connection",
        )
        self._control_socket_path = effective_dir / "control.sock"
        self._probe_socket_path = effective_dir / "probe.sock"
        self._real_control_socket_path = self._connection_dir / "control.sock"

        hosts = get_container_ssh_credentials(job, job_runtime_data=job_runtime_data)
        target, identity = hosts[-1]
        self._tunnel = SSHTunnel(
            destination=f"{target.username}@{target.hostname}",
            port=target.port,
            identity=identity,
            control_sock_path=self._control_socket_path,
            ssh_proxies=hosts[:-1],
            options={
                **SSH_DEFAULT_OPTIONS,
                "ConnectTimeout": str(settings.SERVER_SSH_CONNECT_TIMEOUT),
                "ServerAliveInterval": "10",
                "ServerAliveCountMax": "3",
                "ControlPersist": "2m",
            },
            batch_mode=True,
        )

    async def open(self) -> None:
        if self._real_control_socket_path.exists():
            if await self._tunnel.acheck() and await self._server_is_reachable():
                self._last_verified_at = time.monotonic()
                return
            await self._tunnel.aclose()
            self._real_control_socket_path.unlink(missing_ok=True)

        await self._tunnel.aopen()
        try:
            remote_dir = shlex.quote(str(_REMOTE_SOCKET_PATH.parent))
            remote_socket = shlex.quote(str(_REMOTE_SOCKET_PATH))
            # A new server owner replaces the stable path, making an orphaned forward unreachable.
            await self._tunnel.aexec(
                f"mkdir -p {remote_dir} && chmod 755 {remote_dir} && rm -f {remote_socket}"
            )
            server_socket = _get_server_socket()
            self._tunnel.reverse_forwarded_sockets = [
                SocketPair(
                    local=server_socket,
                    remote=UnixSocket(path=_REMOTE_SOCKET_PATH),
                )
            ]
            # Probe through the job socket itself: a socket path can remain after its listener
            # becomes unreachable.
            self._tunnel.forwarded_sockets = [
                SocketPair(
                    local=UnixSocket(path=self._probe_socket_path),
                    remote=UnixSocket(path=_REMOTE_SOCKET_PATH),
                )
            ]
            await self._tunnel.aopen()
            # The socket carries no credentials. World access inside the isolated job container
            # lets configurations using a non-root `user` reach it as well.
            await self._tunnel.aexec(f"chmod 666 {remote_socket}")
            if not await self._server_is_reachable():
                raise SSHError(
                    "dstack server is not reachable from the job"
                    f" (forward target {server_socket.render()})"
                )
        except Exception:
            await self._tunnel.aclose()
            raise
        self._last_verified_at = time.monotonic()

    async def is_alive(self) -> bool:
        if not self._control_socket_path.exists():
            return False
        now = time.monotonic()
        if now - self._last_verified_at < _MIN_ALIVE_CHECK_INTERVAL:
            return True
        if not await self._tunnel.acheck() or not await self._server_is_reachable():
            return False
        self._last_verified_at = now
        return True

    async def close(self) -> None:
        await self._tunnel.aclose()
        shutil.rmtree(self._connection_dir, ignore_errors=True)

    async def _server_is_reachable(self) -> bool:
        transport = httpx.AsyncHTTPTransport(uds=str(self._probe_socket_path))
        try:
            async with httpx.AsyncClient(
                transport=transport,
                timeout=_PROBE_TIMEOUT,
            ) as client:
                response = await client.get("http://localhost/healthcheck")
        except httpx.HTTPError:
            return False
        return response.status_code == 200


class JobServerConnectionsPool:
    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, JobServerConnection] = {}
        self._failure_started_at: dict[uuid.UUID, float] = {}
        self._locks: WeakValueDictionary[uuid.UUID, asyncio.Lock] = WeakValueDictionary()

    async def ensure(
        self,
        job: JobModel,
        job_runtime_data: Optional[JobRuntimeData],
    ) -> bool:
        lock = self._get_lock(job.id)
        async with lock:
            connection = self._connections.get(job.id)
            if connection is not None and await connection.is_alive():
                self._failure_started_at.pop(job.id, None)
                return True
            if connection is not None:
                await self._close(connection)
                self._connections.pop(job.id, None)

            connection = JobServerConnection(job, job_runtime_data)
            try:
                await connection.open()
            except SSHError as e:
                logger.warning("Failed to establish server access for job %s: %s", job.id, e)
                await self._close(connection)
                self._failure_started_at.setdefault(job.id, time.monotonic())
                return False
            self._connections[job.id] = connection
            self._failure_started_at.pop(job.id, None)
            return True

    def retry_timed_out(self, job_id: uuid.UUID, timeout: float) -> bool:
        failure_started_at = self._failure_started_at.get(job_id)
        if failure_started_at is None:
            return False
        return time.monotonic() - failure_started_at > timeout

    async def remove(self, job_id: uuid.UUID) -> None:
        lock = self._get_lock(job_id)
        async with lock:
            connection = self._connections.pop(job_id, None)
            if connection is not None:
                await self._close(connection)
            self._failure_started_at.pop(job_id, None)
            shutil.rmtree(CONNECTIONS_DIR / str(job_id), ignore_errors=True)

    async def remove_all(self) -> None:
        job_ids = set(self._connections).union(self._failure_started_at)
        await asyncio.gather(*(self.remove(job_id) for job_id in job_ids))

    def _get_lock(self, job_id: uuid.UUID) -> asyncio.Lock:
        # setdefault is atomic under the single-threaded event loop, so no extra lock is needed
        return self._locks.setdefault(job_id, asyncio.Lock())

    @staticmethod
    async def _close(connection: JobServerConnection) -> None:
        try:
            await connection.close()
        except Exception:
            logger.exception("Failed to close server access for job %s", connection.job_id)


job_server_connections_pool = JobServerConnectionsPool()
