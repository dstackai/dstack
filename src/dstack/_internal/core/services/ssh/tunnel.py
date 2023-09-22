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
        user: str = "ubuntu",
        id_rsa: Optional[bytes] = None,
        id_rsa_path: Optional[PathLike] = None,
    ):
        """
        :param ports: Mapping { remote port -> local port }
        """
        if id_rsa is not None and id_rsa_path is not None:
            raise ValueError("Only one of id_rsa and id_rsa_path can be specified")
        if id_rsa is None and id_rsa_path is None:
            raise ValueError("One of id_rsa and id_rsa_path must be specified")

        self.temp_dir = tempfile.TemporaryDirectory(prefix="dstack-")
        # socket path must be shorter than 104 chars
        self.control_sock_path = os.path.join(self.temp_dir.name, "control.sock")
        self.user = user
        self.hostname = hostname
        self.ports = ports
        self.id_rsa_path = id_rsa_path
        if id_rsa is not None:
            self.id_rsa_path = os.path.join(self.temp_dir.name, "id_rsa")
            with open(self.id_rsa_path, "wb", opener=_key_opener) as f:
                f.write(id_rsa)
            os.chmod(f.name, 0o600)

    def open(self):
        command = [
            "ssh",
            "-f",
            "-N",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "ConnectTimeout=1",
            "-M",
            "-S",
            self.control_sock_path,
            "-i",
            self.id_rsa_path,
        ]
        for port_remote, port_local in self.ports.items():
            command += ["-L", f"{port_local}:localhost:{port_remote}"]
        command += [f"{self.user}@{self.hostname}"]

        logger.debug("Starting SSH tunnel: %s", command)
        r = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r.returncode == 0:
            return
        if b": Operation timed out" in r.stderr:
            raise SSHTimeoutError()
        if b": Connection refused" in r.stderr:
            raise SSHConnectionRefusedError()
        if b": Permission denied (publickey)" in r.stderr:
            raise SSHKeyError()
        if b": Address already in use" in r.stderr:
            raise SSHPortInUseError()
        raise SSHError(r.stderr.decode())

    def close(self):
        command = ["ssh", "-S", self.control_sock_path, "-O", "exit", self.hostname]
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def _key_opener(path, flags):
    return os.open(path, flags, 0o600)
