import threading
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Collection, Optional, Union

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
from dstack._internal.server.settings import SERVER_DIR_PATH
from dstack._internal.utils.path import FileContent

PrivateKeyOrPair = Union[str, tuple[str, Optional[str]]]
"""A host private key or pair of (host private key, optional proxy jump private key)"""

CONNECTIONS_DIR = SERVER_DIR_PATH / "instance-connections"

DEFAULT_PORTS_TO_FORWARD = [DSTACK_SHIM_HTTP_PORT, DSTACK_RUNNER_HTTP_PORT]


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
        container_to_host_port_map = InstanceConnection._get_container_to_host_port_map(jpd, jrd)
        return InstanceConnectionKey(
            hostname=jpd.hostname,
            port=jpd.ssh_port,
            ports_to_forward=tuple(container_to_host_port_map.values()),
        )


class InstanceConnectionPool:
    def __init__(self):
        self._connections: dict[InstanceConnectionKey, InstanceConnection] = {}
        self._access_locks: dict[InstanceConnectionKey, threading.Lock] = {}
        self._access_locks_lock = threading.Lock()

    def get_or_open(
        self,
        ssh_private_key: PrivateKeyOrPair,
        jpd: JobProvisioningData,
        jrd: Optional[JobRuntimeData],
    ) -> Optional["InstanceConnection"]:
        key = InstanceConnectionKey.from_jpd(jpd, jrd)
        lock = self._get_access_lock(key)
        with lock:
            conn = self._connections.get(key)
            if conn is not None:
                return conn
            conn = InstanceConnection(ssh_private_key, jpd, jrd)
            try:
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
            conn.close()

    def close_all(self) -> None: ...  # graceful shutdown

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
    def __init__(
        self,
        ssh_private_key: PrivateKeyOrPair,
        jpd: JobProvisioningData,
        jrd: Optional[JobRuntimeData],
    ) -> None:
        self._key = InstanceConnectionKey.from_jpd(jpd, jrd)
        self._connection_dir = (
            CONNECTIONS_DIR
            / f"{self._key.hostname}:{self._key.port}"
            / str(self._key.ports_to_forward)
        )
        self._connection_dir.mkdir(parents=True, exist_ok=True)
        # connection_dir can have a long path that won't be accepted by the ssh command,
        # so we create a short temporary symlink
        self._temp_dir, self._connection_symlink_dir = self._init_symlink_dir(self._connection_dir)
        self._control_socket_path = self._connection_symlink_dir / "control.sock"
        self._container_to_host_port_map = InstanceConnection._get_container_to_host_port_map(
            jpd, jrd
        )
        self._host_port_to_uds_map = InstanceConnection._get_host_port_to_uds_map(
            connection_dir=self._connection_symlink_dir,
            ports_to_forward=self._key.ports_to_forward,
        )
        self._tunnel = SSHTunnel(
            destination=f"{jpd.username}@{jpd.hostname}",
            port=jpd.ssh_port,
            identity=_get_identity(ssh_private_key, jpd),
            control_sock_path=self._control_socket_path,
            forwarded_sockets=self._get_forwarded_sockets(self._host_port_to_uds_map),
            ssh_proxies=_get_proxies(ssh_private_key, jpd),
            options={
                **SSH_DEFAULT_OPTIONS,
                "ServerAliveInterval": "30",
                "ControlPersist": "2m",
            },
            batch_mode=True,
        )

    def open(self) -> None:
        self._tunnel.open()

    def forwarded_path(self, container_port: int) -> Path:
        return self._host_port_to_uds_map[self._container_to_host_port_map[container_port]]

    def close(self) -> None:
        self._tunnel.close()

    @property
    def key(self) -> InstanceConnectionKey:
        return self._key

    @staticmethod
    def _init_symlink_dir(connection_dir: Path) -> tuple[TemporaryDirectory, Path]:
        temp_dir = TemporaryDirectory()
        symlink_dir = Path(temp_dir.name) / "connection"
        symlink_dir.symlink_to(connection_dir, target_is_directory=True)
        return temp_dir, symlink_dir

    @staticmethod
    def _get_container_to_host_port_map(
        jpd: JobProvisioningData,
        jrd: Optional[JobRuntimeData],
    ) -> dict[int, int]:
        port_map = {port: port for port in DEFAULT_PORTS_TO_FORWARD}
        if jrd is not None and jrd.ports is not None:
            port_map.update(jrd.ports)
        return port_map

    @staticmethod
    def _get_host_port_to_uds_map(
        connection_dir: Path,
        ports_to_forward: Collection[int],
    ) -> dict[int, Path]:
        return {port: connection_dir / str(port) for port in ports_to_forward}

    @staticmethod
    def _get_forwarded_sockets(host_port_to_uds_map: dict[int, Path]) -> list[SocketPair]:
        return [
            SocketPair(
                local=UnixSocket(path=path),
                remote=IPSocket(host="localhost", port=port),
            )
            for port, path in host_port_to_uds_map.items()
        ]


def _get_identity(ssh_private_key: PrivateKeyOrPair, jpd: JobProvisioningData) -> FileContent:
    if isinstance(ssh_private_key, tuple):
        ssh_private_key, _ = ssh_private_key
    return FileContent(ssh_private_key)


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
