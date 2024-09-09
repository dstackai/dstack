import abc
import asyncio
import os
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from dstack._internal.core.errors import SSHError
from dstack._internal.core.models.instances import SSHConnectionParams
from dstack._internal.core.services.ssh import get_ssh_error
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import FilePath, FilePathOrContent, PathLike

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
        ssh_config_path: str = "none",
        port: Optional[int] = None,
        ssh_proxy: Optional[SSHConnectionParams] = None,
    ):
        """
        :param forwarded_sockets: Connections to the specified local sockets will be
            forwarded to their corresponding remote sockets
        :param reverse_forwarded_sockets: Connections to the specified remote sockets
            will be forwarded to their corresponding local sockets
        """
        self.destination = destination
        self.forwarded_sockets = list(forwarded_sockets)
        self.reverse_forwarded_sockets = list(reverse_forwarded_sockets)
        self.options = options
        self.port = port
        self.ssh_config_path = ssh_config_path
        self.ssh_proxy = ssh_proxy

        self.temp_dir, self.identity_path, self.control_sock_path = self._init_temp_dir_if_needed(
            identity, control_sock_path
        )

    @staticmethod
    def _init_temp_dir_if_needed(
        identity: FilePathOrContent, control_sock_path: Optional[PathLike]
    ) -> Tuple[Optional[tempfile.TemporaryDirectory], PathLike, PathLike]:
        if control_sock_path is not None and isinstance(identity, FilePath):
            return None, identity.path, control_sock_path

        temp_dir = tempfile.TemporaryDirectory()
        if control_sock_path is None:
            control_sock_path = os.path.join(temp_dir.name, "control.sock")
        if isinstance(identity, FilePath):
            identity_path = identity.path
        else:
            identity_path = os.path.join(temp_dir.name, "identity")
            with open(
                identity_path, opener=lambda path, flags: os.open(path, flags, 0o600), mode="w"
            ) as f:
                f.write(identity.content)

        return temp_dir, identity_path, control_sock_path

    def open_command(self) -> List[str]:
        command = [
            "ssh",
            "-F",
            self.ssh_config_path,
            "-f",  # go to background after connecting
            "-N",  # do not run commands on remote
            "-M",  # use the control socket in master mode
            "-S",
            str(self.control_sock_path),
            "-i",
            str(self.identity_path),
        ]
        if self.port is not None:
            command += ["-p", str(self.port)]
        for k, v in self.options.items():
            command += ["-o", f"{k}={v}"]
        if proxy_command := self.proxy_command():
            command += ["-o", "ProxyCommand=" + shlex.join(proxy_command)]
        for socket_pair in self.forwarded_sockets:
            command += ["-L", f"{socket_pair.local.render()}:{socket_pair.remote.render()}"]
        for socket_pair in self.reverse_forwarded_sockets:
            command += ["-R", f"{socket_pair.remote.render()}:{socket_pair.local.render()}"]
        command += [self.destination]
        return command

    def close_command(self) -> List[str]:
        return ["ssh", "-S", str(self.control_sock_path), "-O", "exit", self.destination]

    def check_command(self) -> List[str]:
        return ["ssh", "-S", str(self.control_sock_path), "-O", "check", self.destination]

    def exec_command(self) -> List[str]:
        return ["ssh", "-S", str(self.control_sock_path), self.destination]

    def proxy_command(self) -> Optional[List[str]]:
        if self.ssh_proxy is None:
            return None
        return [
            "ssh",
            "-i",
            str(self.identity_path),
            "-W",
            "%h:%p",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-p",
            str(self.ssh_proxy.port),
            f"{self.ssh_proxy.username}@{self.ssh_proxy.hostname}",
        ]

    def open(self) -> None:
        # Using stderr=subprocess.PIPE may block subprocess.run.
        # Redirect stderr to file to get ssh error message
        with tempfile.NamedTemporaryFile(delete=False) as f:
            try:
                r = subprocess.run(
                    self.open_command(), stdout=subprocess.DEVNULL, stderr=f, timeout=SSH_TIMEOUT
                )
            except subprocess.TimeoutExpired as e:
                msg = f"SSH tunnel to {self.destination} did not open in {SSH_TIMEOUT} seconds"
                logger.debug(msg)
                raise SSHError(msg) from e
        with open(f.name, "r+b") as f:
            error = f.read()
        os.remove(f.name)
        if r.returncode == 0:
            return
        logger.debug("SSH tunnel failed: %s", error)
        raise get_ssh_error(error)

    async def aopen(self) -> None:
        proc = await asyncio.create_subprocess_exec(
            *self.open_command(), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), SSH_TIMEOUT)
        except asyncio.TimeoutError as e:
            msg = f"SSH tunnel to {self.destination} did not open in {SSH_TIMEOUT} seconds"
            logger.debug(msg)
            raise SSHError(msg) from e
        if proc.returncode == 0:
            return
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
