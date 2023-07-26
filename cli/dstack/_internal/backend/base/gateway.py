import subprocess
from typing import List, Optional

from dstack._internal.core.error import DstackError
from dstack._internal.hub.utils.ssh import HUB_PRIVATE_KEY_PATH
from dstack._internal.utils.common import PathLike


def ssh_copy_id(
    hostname: str,
    public_key: bytes,
    user: str = "ubuntu",
    id_rsa: Optional[PathLike] = HUB_PRIVATE_KEY_PATH,
):
    command = f"echo '{public_key.decode()}' >> ~/.ssh/authorized_keys"
    exec_ssh_command(hostname, command, user=user, id_rsa=id_rsa)


def exec_ssh_command(hostname: str, command: str, user: str, id_rsa: Optional[PathLike]) -> bytes:
    args = ["ssh"]
    if id_rsa is not None:
        args += ["-i", id_rsa]
    args += [
        "-o",
        "StrictHostKeyChecking=accept-new",
        f"{user}@{hostname}",
        command,
    ]
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        raise SSHCommandError(args, stderr.decode())
    return stdout


class SSHCommandError(DstackError):
    def __init__(self, cmd: List[str], message: str):
        super().__init__(message)
        self.cmd = cmd
