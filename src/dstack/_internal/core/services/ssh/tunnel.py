import abc
import asyncio
import os
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Dict, Iterable, List, Literal, Optional, Union

from dstack._internal.core.errors import SSHError
from dstack._internal.core.models.instances import SSHConnectionParams
from dstack._internal.core.services.ssh import get_ssh_error
from dstack._internal.core.services.ssh.client import get_ssh_client_info
from dstack._internal.utils.common import run_async
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import FilePath, FilePathOrContent, PathLike
from dstack._internal.utils.ssh import normalize_path

logger = get_logger(__name__)
SSH_TIMEOUT = 15
SSH_DEFAULT_OPTIONS = {
    "StrictHostKeyChecking": "no",
    "UserKnownHostsFile": "/dev/null",
    "ExitOnForwardFailure": "yes",
    "StreamLocalBindUnlink": "yes",
    "ConnectTimeout": "3",
}


class Socket(abc.ABC):
    @abc.abstractmethod
    def render(self) -> str:
        pass


@dataclass
class UnixSocket(Socket):
    path: PathLike

    def render(self) -> str:
        return str(self.path)


@dataclass
class IPSocket(Socket):
    host: str
    port: int

    def render(self) -> str:
        if ":" in self.host:  # assuming IPv6
            return f"[{self.host}]:{self.port}"
        return f"{self.host}:{self.port}"


@dataclass
class SocketPair:
    local: Socket
    remote: Socket


class SSHTunnel:
    def __init__(
        self,
        destination: str,
        identity: FilePathOrContent,
        forwarded_sockets: Iterable[SocketPair] = (),
        reverse_forwarded_sockets: Iterable[SocketPair] = (),
        control_sock_path: Optional[PathLike] = None,
        options: Dict[str, str] = SSH_DEFAULT_OPTIONS,
        ssh_config_path: Union[PathLike, Literal["none"]] = "none",
        port: Optional[int] = None,
        ssh_proxies: Iterable[tuple[SSHConnectionParams, Optional[FilePathOrContent]]] = (),
    ):
        """
        :param forwarded_sockets: Connections to the specified local sockets will be
            forwarded to their corresponding remote sockets
        :param reverse_forwarded_sockets: Connections to the specified remote sockets
            will be forwarded to their corresponding local sockets
        :param ssh_proxies: pairs of SSH connections params and optional identities,
            in order from outer to inner. If an identity is `None`, the `identity` param
            is used instead.
        """
        self.destination = destination
        self.forwarded_sockets = list(forwarded_sockets)
        self.reverse_forwarded_sockets = list(reverse_forwarded_sockets)
        self.options = options
        self.port = port
        self.ssh_config_path = normalize_path(ssh_config_path)
        temp_dir = tempfile.TemporaryDirectory()
        self.temp_dir = temp_dir
        if control_sock_path is None:
            control_sock_path = os.path.join(temp_dir.name, "control.sock")
        self.control_sock_path = normalize_path(control_sock_path)
        self.identity_path = normalize_path(self._get_identity_path(identity, "identity"))
        self.ssh_proxies: list[tuple[SSHConnectionParams, PathLike]] = []
        for proxy_index, (proxy_params, proxy_identity) in enumerate(ssh_proxies):
            if proxy_identity is None:
                proxy_identity_path = self.identity_path
            else:
                proxy_identity_path = self._get_identity_path(
                    proxy_identity, f"proxy_identity_{proxy_index}"
                )
            self.ssh_proxies.append((proxy_params, proxy_identity_path))
        self.log_path = normalize_path(os.path.join(temp_dir.name, "tunnel.log"))
        self.ssh_client_info = get_ssh_client_info()
        self.ssh_exec_path = str(self.ssh_client_info.path)

    def open_command(self) -> List[str]:
        # Some information about how `ssh(1)` handles options:
        # 1. Command-line options override config options regardless of the order of the arguments:
        #   `ssh -S sock2 -F config` with `ControlPath sock1` in the config -> the control socket
        #   path is `sock2`.
        # 2. First argument wins:
        #   `ssh -S sock2 -S sock1` -> the control socket path is `sock2`.
        # 3. `~` is not expanded in the arguments, but expanded in the config file.
        command = [
            self.ssh_exec_path,
            "-F",
            self.ssh_config_path,
            "-i",
            self.identity_path,
            "-E",
            self.log_path,
            "-N",  # do not run commands on remote
        ]
        if self.ssh_client_info.supports_background_mode:
            command += ["-f"]  # go to background after successful authentication
        else:
            raise SSHError("Unsupported SSH client")
        if self.ssh_client_info.supports_control_socket:
            # It's safe to use ControlMaster even if the ssh client does not support multiplexing
            # as long as we don't allow more than one tunnel to the specific host to be running.
            # We use this feature for control only (see :meth:`close_command`).
            command += [
                # Not `-M`, which means `ControlMaster=yes`, to avoid spawning uncontrollable
                # ssh instances if more than one tunnel is started (precaution).
                "-o",
                "ControlMaster=auto",
                "-S",
                self.control_sock_path,
            ]
        else:
            raise SSHError("Unsupported SSH client")
        if self.port is not None:
            command += ["-p", str(self.port)]
        for k, v in self.options.items():
            command += ["-o", f"{k}={v}"]
        if proxy_command := self._get_proxy_command():
            command += ["-o", proxy_command]
        for socket_pair in self.forwarded_sockets:
            command += ["-L", f"{socket_pair.local.render()}:{socket_pair.remote.render()}"]
        for socket_pair in self.reverse_forwarded_sockets:
            command += ["-R", f"{socket_pair.remote.render()}:{socket_pair.local.render()}"]
        command += [self.destination]
        return command

    def close_command(self) -> List[str]:
        return [self.ssh_exec_path, "-S", self.control_sock_path, "-O", "exit", self.destination]

    def check_command(self) -> List[str]:
        return [self.ssh_exec_path, "-S", self.control_sock_path, "-O", "check", self.destination]

    def exec_command(self) -> List[str]:
        return [self.ssh_exec_path, "-S", self.control_sock_path, self.destination]

    def open(self) -> None:
        # We cannot use `stderr=subprocess.PIPE` here since the forked process (daemon) does not
        # close standard streams if ProxyJump is used, therefore we will wait EOF from the pipe
        # as long as the daemon exists.
        self._remove_log_file()
        try:
            r = subprocess.run(
                self.open_command(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=SSH_TIMEOUT,
            )
        except subprocess.TimeoutExpired as e:
            msg = f"SSH tunnel to {self.destination} did not open in {SSH_TIMEOUT} seconds"
            logger.debug(msg)
            raise SSHError(msg) from e
        if r.returncode == 0:
            return
        stderr = self._read_log_file()
        logger.debug("SSH tunnel failed: %s", stderr)
        raise get_ssh_error(stderr)

    async def aopen(self) -> None:
        await run_async(self._remove_log_file)
        proc = await asyncio.create_subprocess_exec(
            *self.open_command(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        try:
            await asyncio.wait_for(proc.communicate(), SSH_TIMEOUT)
        except asyncio.TimeoutError as e:
            proc.kill()
            msg = f"SSH tunnel to {self.destination} did not open in {SSH_TIMEOUT} seconds"
            logger.debug(msg)
            raise SSHError(msg) from e
        if proc.returncode == 0:
            return
        stderr = await run_async(self._read_log_file)
        logger.debug("SSH tunnel failed: %s", stderr)
        raise get_ssh_error(stderr)

    def close(self) -> None:
        subprocess.run(self.close_command(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    async def aclose(self) -> None:
        proc = await asyncio.create_subprocess_exec(
            *self.close_command(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        await proc.wait()

    async def acheck(self) -> bool:
        proc = await asyncio.create_subprocess_exec(
            *self.check_command(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        await proc.wait()
        ok = proc.returncode == 0
        return ok

    async def aexec(self, command: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            *self.exec_command(), command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise SSHError(stderr.decode())
        return stdout.decode()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _get_proxy_command(self) -> Optional[str]:
        proxy_command: Optional[str] = None
        for params, identity_path in self.ssh_proxies:
            proxy_command = self._build_proxy_command(params, identity_path, proxy_command)
        return proxy_command

    def _build_proxy_command(
        self,
        params: SSHConnectionParams,
        identity_path: PathLike,
        prev_proxy_command: Optional[str],
    ) -> Optional[str]:
        command = [
            self.ssh_exec_path,
            "-i",
            identity_path,
            "-W",
            "%h:%p",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
        ]
        if prev_proxy_command is not None:
            command += ["-o", prev_proxy_command.replace("%", "%%")]
        command += [
            "-p",
            str(params.port),
            f"{params.username}@{params.hostname}",
        ]
        return "ProxyCommand=" + shlex.join(command)

    def _read_log_file(self) -> bytes:
        with open(self.log_path, "rb") as f:
            return f.read()

    def _remove_log_file(self) -> None:
        try:
            os.remove(self.log_path)
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.debug("Failed to remove SSH tunnel log file %s: %s", self.log_path, e)

    def _get_identity_path(self, identity: FilePathOrContent, tmp_filename: str) -> PathLike:
        if isinstance(identity, FilePath):
            return identity.path
        identity_path = os.path.join(self.temp_dir.name, tmp_filename)
        with open(
            identity_path, opener=lambda path, flags: os.open(path, flags, 0o600), mode="w"
        ) as f:
            f.write(identity.content)
        return identity_path


def ports_to_forwarded_sockets(
    ports: Dict[int, int], bind_local: str = "localhost"
) -> List[SocketPair]:
    """
    Converts remote->local ports mapping to List[SocketPair] suitable for SSHTunnel
    """
    return [
        SocketPair(
            local=IPSocket(host=bind_local, port=port_local),
            remote=IPSocket(host="localhost", port=port_remote),
        )
        for port_remote, port_local in ports.items()
    ]
