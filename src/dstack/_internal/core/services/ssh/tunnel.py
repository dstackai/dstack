import os
import subprocess
import tempfile
from typing import Dict, Optional

from dstack._internal.core.errors import DstackError
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import PathLike

logger = get_logger(__name__)


class SSHError(DstackError):
    pass


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
        hostname: str,
        ports: Dict[int, int],
        *,
        user: Optional[str] = "ubuntu",
        ssh_port: Optional[int] = None,
        id_rsa: Optional[bytes] = None,
        id_rsa_path: Optional[PathLike] = None,
        control_sock_path: Optional[PathLike] = None,
        options: Optional[Dict[str, str]] = None,
    ):
        """
        :param ports: Mapping { remote port -> local port }
        """
        if id_rsa is not None and id_rsa_path is not None:
            raise ValueError("Only one of id_rsa and id_rsa_path can be specified")
        if id_rsa is None and id_rsa_path is None:
            raise ValueError("One of id_rsa and id_rsa_path must be specified")

        self.temp_dir = tempfile.TemporaryDirectory(prefix="dstack-")
        if user is None:
            self.host = hostname
        else:
            self.host = f"{user}@{hostname}"
        self.ports = ports
        self.id_rsa_path = id_rsa_path
        if id_rsa is not None:
            self.id_rsa_path = os.path.join(self.temp_dir.name, "id_rsa")
            with open(self.id_rsa_path, "wb", opener=_key_opener) as f:
                f.write(id_rsa)
        if options is None:
            self.options = {
                "StrictHostKeyChecking": "no",
                "UserKnownHostsFile": "/dev/null",
                "ExitOnForwardFailure": "yes",
                "ConnectTimeout": "1",
            }
        else:
            self.options = options
        if ssh_port is not None:
            self.options["Port"] = str(ssh_port)
        if control_sock_path is None:
            self.control_sock_path = os.path.join(self.temp_dir.name, "control.sock")
        else:
            self.control_sock_path = str(control_sock_path)
        self.options["ControlMaster"] = "auto"
        self.options["ControlPath"] = self.control_sock_path

    def open(self):
        command = ["ssh", "-f", "-N", "-i", self.id_rsa_path]
        for k, v in self.options.items():
            command += ["-o", f"{k}={v}"]
        for port_remote, port_local in self.ports.items():
            command += ["-L", f"{port_local}:localhost:{port_remote}"]
        command += [self.host]

        logger.debug("Starting SSH tunnel: %s", command)
        r = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r.returncode == 0:
            return
        if b": Operation timed out" in r.stderr:
            raise SSHTimeoutError()
        if b": Connection refused" in r.stderr:
            raise SSHConnectionRefusedError()
        if b": Permission denied (publickey)" in r.stderr:
            raise SSHKeyError(r.stderr)
        if b": Address already in use" in r.stderr:
            raise SSHPortInUseError()
        raise SSHError(r.stderr.decode())

    def close(self):
        command = ["ssh", "-S", self.control_sock_path, "-O", "exit", self.host]
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def _key_opener(path, flags):
    return os.open(path, flags, 0o600)
