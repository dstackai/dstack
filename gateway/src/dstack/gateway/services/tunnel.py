import logging
import os
import shlex
import shutil
import subprocess
import tempfile
from typing import List, Optional

from pydantic import BaseModel

from dstack.gateway.errors import SSHError

logger = logging.getLogger(__name__)


class SSHTunnel(BaseModel):
    """
    SSHTunnel represents a control to start, stop and check an SSH tunnel status.
    Its internal state could be serialized to a file and restored from it using pydantic.
    """

    temp_dir: str
    start_cmd: List[str]
    exit_cmd: List[str]
    check_cmd: List[str]

    @classmethod
    def create(
        cls,
        host: str,
        port: int,
        app_port: int,
        *,
        id_rsa_path: str = "~/.ssh/id_rsa",
        docker_host: Optional[str] = None,
        docker_port: Optional[int] = None,
    ) -> "SSHTunnel":
        temp_dir = tempfile.mkdtemp()
        os.chmod(temp_dir, 0o755)  # grant any user read access
        control_path = f"{temp_dir}/control"

        cmd = ["ssh", "-i", id_rsa_path, "-M", "-S", control_path]
        cmd += ["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]
        cmd += ["-o", "StreamLocalBindMask=0111", "-o", "StreamLocalBindUnlink=yes"]
        cmd += ["-o", "ServerAliveInterval=60"]
        cmd += ["-f", "-N", "-L", f"{_sock_path(temp_dir)}:localhost:{app_port}"]
        if docker_host is not None:
            # use `host` as a jump host
            proxy = ["ssh", "-i", id_rsa_path, "-W", "%h:%p"]
            proxy += ["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]
            proxy += ["-p", str(port), host]
            cmd += ["-o", f"ProxyCommand={shlex.join(proxy)}"]
            # connect to `docker_host`
            cmd += ["-p", str(docker_port), docker_host]
        else:
            # connect to `host` directly
            cmd += ["-p", str(port), host]

        start_cmd = cmd
        exit_cmd = ["ssh", "-S", control_path, "-O", "exit"]
        check_cmd = ["ssh", "-S", control_path, "-O", "check"]
        return cls(temp_dir=temp_dir, start_cmd=start_cmd, exit_cmd=exit_cmd, check_cmd=check_cmd)

    @property
    def sock_path(self):
        return _sock_path(self.temp_dir)

    def start(self):
        logger.info("Starting SSH tunnel for %s", self.sock_path)
        logger.debug("Executing %s", shlex.join(self.start_cmd))
        try:
            # do not capture output or it hangs
            r = subprocess.run(self.start_cmd, timeout=10)
        except subprocess.TimeoutExpired:
            raise SSHError("Timeout exceeded")
        if r.returncode != 0:
            raise SSHError("SSH tunnel failed to start")

    def stop(self):
        logger.info("Stopping SSH tunnel for %s", self.sock_path)
        r = subprocess.run(self.exit_cmd, timeout=5, capture_output=True)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # TODO(egor-s): retry ssh tunnel
    # TODO(egor-s): invoke callback on ssh tunnel status change


def _sock_path(temp_dir: str) -> str:
    return f"{temp_dir}/sock"
