import os
import shlex
import subprocess
import tempfile
from typing import Dict, Optional

from dstack._internal.core.models.instances import SSHConnectionParams
from dstack._internal.core.services.ssh import get_ssh_error
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import PathLike

logger = get_logger(__name__)


class SSHTunnel:
    def __init__(
        self,
        host: str,
        id_rsa_path: PathLike,
        ports: Dict[int, int],
        control_sock_path: PathLike,
        options: Dict[str, str],
        ssh_config_path: str = "none",
    ):
        """
        :param ports: Mapping { remote port -> local port }
        """
        self.host = host
        self.id_rsa_path = id_rsa_path
        self.ports = ports
        self.control_sock_path = control_sock_path
        self.options = options
        self.ssh_config_path = ssh_config_path

    def open(self):
        # ControlMaster and ControlPath are always set
        command = [
            "ssh",
            "-F",
            self.ssh_config_path,
            "-f",
            "-N",
            "-M",
            "-S",
            self.control_sock_path,
            "-i",
            self.id_rsa_path,
        ]
        for k, v in self.options.items():
            command += ["-o", f"{k}={v}"]
        for port_remote, port_local in self.ports.items():
            command += ["-L", f"{port_local}:localhost:{port_remote}"]
        command += [self.host]
        # Using stderr=subprocess.PIPE may block subprocess.run.
        # Redirect stderr to file to get ssh error message
        with tempfile.NamedTemporaryFile(delete=False) as f:
            r = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=f)
        with open(f.name, "r+b") as f:
            error = f.read()
        os.remove(f.name)
        if r.returncode == 0:
            return
        logger.debug("SSH tunnel failed: %s", error)
        raise get_ssh_error(error)

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
        ssh_proxy: Optional[SSHConnectionParams] = None,
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
        options = {}
        if ssh_proxy is not None:
            proxy_command = ["ssh", "-i", id_rsa_path, "-W", "%h:%p"]
            proxy_command += [
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
            ]
            proxy_command += [
                "-p",
                str(ssh_proxy.port),
                f"{ssh_proxy.username}@{ssh_proxy.hostname}",
            ]
            options["ProxyCommand"] = shlex.join(proxy_command)
        options.update(
            {
                "StrictHostKeyChecking": "no",
                "UserKnownHostsFile": "/dev/null",
                "ExitOnForwardFailure": "yes",
                "ConnectTimeout": "3",
                # "ControlPersist": f"{disconnect_delay}s",
                "Port": str(ssh_port),
            }
        )
        super().__init__(
            host=f"{user}@{hostname}",
            id_rsa_path=id_rsa_path,
            ports=ports,
            control_sock_path=control_sock_path,
            options=options,
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

    def __init__(
        self,
        host: str,
        ports: Dict[int, int],
        id_rsa_path: PathLike,
        ssh_config_path: str,
        control_sock_path: Optional[str] = None,
    ):
        if control_sock_path is None:
            self.temp_dir = tempfile.TemporaryDirectory()
            control_sock_path = os.path.join(self.temp_dir.name, "control.sock")
        super().__init__(
            host=host,
            id_rsa_path=id_rsa_path,
            ports=ports,
            control_sock_path=control_sock_path,
            options={},
            ssh_config_path=ssh_config_path,
        )
