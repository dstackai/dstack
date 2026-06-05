import os
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Collection, Optional, Union
from weakref import WeakValueDictionary

from dstack._internal.core.consts import DSTACK_RUNNER_HTTP_PORT, DSTACK_SHIM_HTTP_PORT
from dstack._internal.core.errors import SSHError
from dstack._internal.core.models.instances import SSHConnectionParams
from dstack._internal.core.models.runs import JobProvisioningData, JobRuntimeData
from dstack._internal.core.services.ssh.tunnel import (
    SSH_DEFAULT_OPTIONS,
    IPSocket,
    SocketPair,
    SSHTunnel,
    UnixSocket,
)
from dstack._internal.server.settings import (
    SERVER_DIR_PATH,
    SERVER_SSH_CONNECT_TIMEOUT,
)
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import FileContent, make_tmp_symlink_to_dir

logger = get_logger(__name__)

PrivateKeyOrPair = Union[str, tuple[str, Optional[str]]]
"""A host private key or pair of (host private key, optional proxy jump private key)"""

CONNECTIONS_DIR = SERVER_DIR_PATH / "instance-connections"

MIN_ALIVE_CHECK_INTERVAL = 30
"""How often (at most) `InstanceConnection.is_alive()` runs `ssh -O check`, in seconds."""


@dataclass(frozen=True)
class InstanceConnectionKey:
    hostname: str
    port: int
    ports_to_forward: tuple[int, ...]

    @staticmethod
    def from_jpd(
        jpd: JobProvisioningData, jrd: Optional[JobRuntimeData]
    ) -> "InstanceConnectionKey":
        assert jpd.hostname is not None and jpd.ssh_port is not None
        container_to_host_port_map = InstanceConnection.get_container_to_host_port_map(jpd, jrd)
        return InstanceConnectionKey(
            hostname=jpd.hostname,
            port=jpd.ssh_port,
            ports_to_forward=tuple(container_to_host_port_map.values()),
        )


# InstanceConnectionPool has sync interface because runner/shim clients and all the callers are sync.
# TODO: Consider moving all of them to async for consistency with other pools/clients.
class InstanceConnectionPool:
    """
    A pool of SSH connections to instances' host sshd (VM-based)
    or runner sshd (container-based) for forwarding shim and runner ports.

    NOTE: The pool is not currently intended for arbitrary ports forwarding, only for shim and runner ports.
    E.g. it cannot be used to forward services ports for probes or router-worker communication.
    This simplified model allows forwarding the same ports for the given host:port and reusing the connection across all calls.
    TODO: Generalize to support arbitrary ports forwarding incl. job's ports.

    Incompatible with multiple server processes sharing the same server dir:
    connection dirs and control sockets are assumed to be owned by a single process.
    """

    def __init__(self):
        self._connections: dict[InstanceConnectionKey, InstanceConnection] = {}
        # Use `WeakValueDictionary` for automatic GC of unused locks and avoid manual refcounting.
        # A lock is expected to exist only while a thread holds a strong reference to it.
        self._access_locks: WeakValueDictionary[InstanceConnectionKey, threading.Lock] = (
            WeakValueDictionary()
        )
        self._access_locks_lock = threading.Lock()
        self._closed = False

    def get_or_open(
        self,
        ssh_private_key: PrivateKeyOrPair,
        jpd: JobProvisioningData,
        jrd: Optional[JobRuntimeData],
    ) -> Optional["InstanceConnection"]:
        """
        Starts a new SSH connection or returns an existing one.
        Existing connections are checked for health periodically
        so that subsequent calls to `get_or_open()` eventually return a healthy connection.
        """
        key = InstanceConnectionKey.from_jpd(jpd, jrd)
        lock = self._get_access_lock(key)
        with lock:
            if self._closed:
                return None
            conn = self._connections.get(key)
            if conn is not None:
                if conn.is_alive():
                    return conn
                # The master process is gone — evict and reopen.
                logger.debug("Instance connection %s is dead, reopening", key)
                self._connections.pop(key)
                try:
                    conn.close()
                except Exception:
                    logger.exception("Failed to close instance connection %s", key)
            try:
                conn = InstanceConnection(ssh_private_key, jpd, jrd)
                conn.open()
            except SSHError:
                # error logged in tunnel
                return None
            self._connections[key] = conn
            return conn

    def drop(self, key: InstanceConnectionKey) -> None:
        lock = self._get_access_lock(key)
        with lock:
            try:
                conn = self._connections.pop(key)
            except KeyError:
                return
            try:
                conn.close()
            except Exception:
                logger.exception("Failed to close instance connection %s", key)

    def startup_cleanup(self) -> None:
        """
        Removes connection dirs left by a previous server process (e.g. after SIGKILL).
        Must be called on server startup before the pool is used.
        Leftover live masters are reaped by `ControlPersist`.
        """
        shutil.rmtree(CONNECTIONS_DIR, ignore_errors=True)

    def close_all(self) -> None:
        """
        Closes all connections and prevents new ones from being opened.
        Safe to call concurrently with in-flight `get_or_open()` calls.
        `get_or_open()` will return `None` after `close_all()`.
        """
        with self._access_locks_lock:
            self._closed = True
            # self._connections holds cached connections, and
            # self._access_locks may hold mid-open connections not yet cached.
            keys = set(self._connections) | set(self._access_locks.keys())
        logger.debug("Closing %d instance connection(s)", len(keys))
        for key in keys:
            self.drop(key)

    def _get_access_lock(self, key: InstanceConnectionKey) -> threading.Lock:
        with self._access_locks_lock:
            lock = self._access_locks.get(key)
            if lock is not None:
                return lock
            lock = threading.Lock()
            self._access_locks[key] = lock
            return lock


instance_connection_pool = InstanceConnectionPool()


class InstanceConnection:
    """
    An SSH connection to instance's host sshd (VM-based)
    or runner sshd (container-based) for forwarding shim and runner ports.

    The same control socket is used for all connections to the same hostname:port,
    unless jrd overrides the runner port mapped on host (blocks case).
    In case of blocks, each job establishes a separate connection with a different runner port forwarded.
    TODO: Re-use the same SSH connection for all blocks via `-O forward`/`-O cancel`.
    """

    def __init__(
        self,
        ssh_private_key: PrivateKeyOrPair,
        jpd: JobProvisioningData,
        jrd: Optional[JobRuntimeData],
        ephemeral: bool = False,
    ) -> None:
        """
        Args:
            ephemeral: Creates a unique tmp dir for the UDS. Use when connection re-use is not needed.
        """
        self._key = InstanceConnectionKey.from_jpd(jpd, jrd)
        self._ephemeral = ephemeral
        self._last_verified_at: float = 0.0
        self._temp_dir, self._effective_conn_dir, self._real_conn_dir = (
            InstanceConnection._resolve_conn_dir(self._key, ephemeral)
        )
        self._control_socket_path = self._effective_conn_dir / "control.sock"
        self._real_control_socket_path = self._real_conn_dir / "control.sock"
        self._container_to_host_port_map = InstanceConnection.get_container_to_host_port_map(
            jpd, jrd
        )
        self._host_port_to_uds_map = InstanceConnection._get_host_port_to_uds_map(
            conn_dir=self._effective_conn_dir,
            ports_to_forward=self._key.ports_to_forward,
        )
        self._tunnel = SSHTunnel(
            destination=f"{jpd.username}@{jpd.hostname}",
            port=jpd.ssh_port,
            identity=InstanceConnection._get_identity(ssh_private_key),
            control_sock_path=self._control_socket_path,
            forwarded_sockets=self._get_forwarded_sockets(self._host_port_to_uds_map),
            ssh_proxies=InstanceConnection._get_proxies(ssh_private_key, jpd),
            options={
                **SSH_DEFAULT_OPTIONS,
                "ConnectTimeout": str(SERVER_SSH_CONNECT_TIMEOUT),
                # Auto-close half-opened connections (the instance not responding).
                "ServerAliveInterval": "10",
                "ServerAliveCountMax": "3",
                # Set ControlPersist to auto-close orphaned background ssh process
                # in case dstack server shutdown is not graceful.
                "ControlPersist": "2m",
            },
            batch_mode=True,
        )

    def open(self) -> None:
        # A control socket left by a killed master or by a master that exited after
        # its tmp symlink was deleted prevents ssh from becoming a mux master
        # ("ControlSocket ... already exists, disabling multiplexing").
        # Remove it unless it's served by a live master (then open() attaches to it).
        if self._real_control_socket_path.exists() and not self._tunnel.check():
            self._real_control_socket_path.unlink(missing_ok=True)
        self._tunnel.open()
        self._last_verified_at = time.monotonic()

    def is_alive(self) -> bool:
        """
        Verifies that the connection's SSH master process is alive:

        1. The control socket exists (a stat). Catches cleanly exited masters (incl. ControlPersist).
        2. `ssh -O check`. Catches killed masters that left a stale socket file behind.
            Rate-limited to once per `MIN_ALIVE_CHECK_INTERVAL`.

        Does not detect half-open TCP (ServerAliveInterval converts it into a clean exit)
        or mid-request deaths (handled by the callers' drop-on-error pattern).
        """
        if not self._control_socket_path.exists():
            return False
        now = time.monotonic()
        if now - self._last_verified_at < MIN_ALIVE_CHECK_INTERVAL:
            return True
        if not self._tunnel.check():
            return False
        # Keep the symlink fresh so that age-based /tmp cleanup is less likely to remove it.
        try:
            os.utime(self._effective_conn_dir, follow_symlinks=False)
        except OSError:
            pass
        self._last_verified_at = now
        return True

    def forwarded_paths(self) -> dict[int, Path]:
        """Returns a mapping from container port to the local UDS path."""
        return {
            container_port: self._host_port_to_uds_map[host_port]
            for container_port, host_port in self._container_to_host_port_map.items()
        }

    def close(self) -> None:
        self._tunnel.close()
        # Remove a stale control.sock left by a killed master, forwarded UDS files
        # (ssh does not unlink them on exit), and the dir itself, so that
        # CONNECTIONS_DIR does not accumulate dirs of gone instances.
        # A master that survives close() because it is unreachable via a deleted
        # symlink is reaped by ControlPersist.
        shutil.rmtree(self._real_conn_dir, ignore_errors=True)

    @property
    def key(self) -> InstanceConnectionKey:
        return self._key

    @staticmethod
    def get_container_to_host_port_map(
        jpd: JobProvisioningData,
        jrd: Optional[JobRuntimeData],
    ) -> dict[int, int]:
        runner_host_port = DSTACK_RUNNER_HTTP_PORT
        if jrd is not None and jrd.ports is not None:
            runner_host_port = jrd.ports.get(DSTACK_RUNNER_HTTP_PORT, runner_host_port)
        port_map = {DSTACK_RUNNER_HTTP_PORT: runner_host_port}
        if jpd.dockerized:
            port_map[DSTACK_SHIM_HTTP_PORT] = DSTACK_SHIM_HTTP_PORT
        return port_map

    @staticmethod
    def _resolve_conn_dir(
        key: InstanceConnectionKey, ephemeral: bool
    ) -> tuple[TemporaryDirectory, Path, Path]:
        """
        Returns (temp dir to retain, dir to be used by ssh, real conn dir).
        """
        if ephemeral:
            temp_dir = TemporaryDirectory()
            path = Path(temp_dir.name)
            return temp_dir, path, path

        conn_dir = (
            CONNECTIONS_DIR
            / f"{key.hostname}:{key.port},{','.join(map(str, key.ports_to_forward))}"
        )
        conn_dir.mkdir(parents=True, exist_ok=True)
        # Connection_dir can have a long path that won't be accepted by the ssh command,
        # so we create a short temporary symlink.
        # The symlink may be removed by age-based /tmp cleanup while the connection is still alive.
        # The connection dir will be removed and the connection is re-opened.
        temp_dir, conn_symlink_dir = make_tmp_symlink_to_dir(
            dirpath=conn_dir,
            symlink_dirname="connection",
        )
        return temp_dir, conn_symlink_dir, conn_dir

    @staticmethod
    def _get_host_port_to_uds_map(
        conn_dir: Path,
        ports_to_forward: Collection[int],
    ) -> dict[int, Path]:
        return {port: conn_dir / f"{port}.sock" for port in ports_to_forward}

    @staticmethod
    def _get_forwarded_sockets(host_port_to_uds_map: dict[int, Path]) -> list[SocketPair]:
        return [
            SocketPair(
                local=UnixSocket(path=path),
                remote=IPSocket(host="localhost", port=port),
            )
            for port, path in host_port_to_uds_map.items()
        ]

    @staticmethod
    def _get_identity(ssh_private_key: PrivateKeyOrPair) -> FileContent:
        if isinstance(ssh_private_key, tuple):
            ssh_private_key, _ = ssh_private_key
        return FileContent(ssh_private_key)

    @staticmethod
    def _get_proxies(
        ssh_private_key: PrivateKeyOrPair, jpd: JobProvisioningData
    ) -> list[tuple[SSHConnectionParams, FileContent]]:
        if jpd.ssh_proxy is None:
            return []

        if isinstance(ssh_private_key, str):
            ssh_proxy_private_key = ssh_private_key
        else:
            ssh_proxy_private_key = ssh_private_key[1]
            if ssh_proxy_private_key is None:
                # In case proxy key is None, fallback to main key (k8s case).
                ssh_proxy_private_key = ssh_private_key[0]

        proxy_identity = FileContent(ssh_proxy_private_key)
        return [(jpd.ssh_proxy, proxy_identity)]
