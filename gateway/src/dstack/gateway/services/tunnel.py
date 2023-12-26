import logging
import os
import shlex
import subprocess
import tempfile
from typing import Optional

from dstack.gateway.errors import SSHError

logger = logging.getLogger(__name__)


class SSHTunnel:
    def __init__(
        self,
        host: str,
        port: int,
        app_port: int,
        *,
        id_rsa_path: str = "~/.ssh/id_rsa",
        docker_host: Optional[str] = None,
        docker_port: Optional[int] = None,
    ):
        self.temp_dir = tempfile.TemporaryDirectory()
        os.chmod(self.temp_dir.name, 0o755)  # grant any user read access
        control_path = f"{self.temp_dir.name}/control"

        cmd = ["ssh", "-i", id_rsa_path, "-M", "-S", control_path]
        cmd += ["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]
        cmd += ["-o", "StreamLocalBindMask=0111", "-o", "StreamLocalBindUnlink=yes"]
        cmd += ["-o", "ServerAliveInterval=60"]
        cmd += ["-f", "-N", "-L", f"{self.sock_path}:localhost:{app_port}"]
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

        self.start_cmd = cmd
        self.exit_cmd = ["ssh", "-S", control_path, "-O", "exit"]
        self.check_cmd = ["ssh", "-S", control_path, "-O", "check"]

    @property
    def sock_path(self):
        return f"{self.temp_dir.name}/sock"

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

    # TODO(egor-s): retry ssh tunnel
    # TODO(egor-s): invoke callback on ssh tunnel status change
