import os
import subprocess
import tempfile
from typing import Dict, Optional

from dstack._internal.core.errors import SSHError
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import PathLike

logger = get_logger(__name__)


class SSHTimeoutError(SSHError):
    pass


class SSHConnectionRefusedError(SSHError):
    pass


class SSHKeyError(SSHError):
    pass


class SSHPortInUseError(SSHError):
    pass


class SSHTunnel:
    def __init__(
        self,
        host: str,
        id_rsa_path: PathLike,
        ports: Dict[int, int],
        control_sock_path: PathLike,
        options: Dict[str, str],
    ):
        """
        :param ports: Mapping { remote port -> local port }
        """
        self.host = host
        self.id_rsa_path = id_rsa_path
        self.ports = ports
        self.control_sock_path = control_sock_path
        self.options = options

    def open(self):
        # ControlMaster and ControlPath are always set
        command = ["ssh", "-f", "-N", "-M", "-S", self.control_sock_path, "-i", self.id_rsa_path]
        for k, v in self.options.items():
            command += ["-o", f"{k}={v}"]
        for port_remote, port_local in self.ports.items():
            command += ["-L", f"{port_local}:localhost:{port_remote}"]
        command += [self.host]

        r = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r.returncode == 0:
            return
        logger.debug("SSH tunnel failed: %s", r.stderr)
        if b": Operation timed out" in r.stderr:
            raise SSHTimeoutError()
        if b": Connection refused" in r.stderr:
            raise SSHConnectionRefusedError()
        if b": Permission denied (publickey)" in r.stderr:
            raise SSHKeyError(r.stderr)
        if b": Address already in use" in r.stderr:
            raise SSHPortInUseError()
        # TODO: kex_exchange_identification: read: Connection reset by peer
        # TODO: Connection timed out during banner exchange
        raise SSHError(r.stderr.decode())

    def close(self):
        command = ["ssh", "-S", self.control_sock_path, "-O", "exit", self.host]
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class RunnerTunnel(SSHTunnel):
    """
    RunnerTunnel cancel forwarding without closing the connection on close()
    """

    def __init__(
        self,
        hostname: str,
        ssh_port: int,
        user: str,
        ports: Dict[int, int],
        id_rsa: str,
        *,
        control_sock_path: Optional[PathLike] = None,
        disconnect_delay: int = 5,
    ):
        self.temp_dir = tempfile.TemporaryDirectory()
        id_rsa_path = os.path.join(self.temp_dir.name, "id_rsa")
        with open(
            id_rsa_path, opener=lambda path, flags: os.open(path, flags, 0o600), mode="w"
        ) as f:
            f.write(id_rsa)
        if control_sock_path is None:
            control_sock_path = os.path.join(self.temp_dir.name, "control.sock")
        super().__init__(
            host=f"{user}@{hostname}",
            id_rsa_path=id_rsa_path,
            ports=ports,
            control_sock_path=control_sock_path,
            options={
                "StrictHostKeyChecking": "no",
                "UserKnownHostsFile": "/dev/null",
                "ExitOnForwardFailure": "yes",
                "ConnectTimeout": "1",
                # "ControlPersist": f"{disconnect_delay}s",
                "Port": ssh_port,
            },
        )

    # def close(self):
    #     # cancel forwarding without closing the connection
    #     command = ["ssh", "-S", self.control_sock_path, "-O", "cancel"]
    #     for port_remote, port_local in self.ports.items():
    #         command += ["-L", f"{port_local}:localhost:{port_remote}"]
    #     command += [self.host]
    #     subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class ClientTunnel(SSHTunnel):
    """
    CLITunnel connects to the host from ssh config
    """

    def __init__(self, host: str, ports: Dict[int, int], id_rsa_path: PathLike):
        self.temp_dir = tempfile.TemporaryDirectory()
        super().__init__(
            host=host,
            id_rsa_path=id_rsa_path,
            ports=ports,
            control_sock_path=os.path.join(self.temp_dir.name, "control.sock"),
            options={},
        )
