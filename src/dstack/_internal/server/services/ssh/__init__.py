import asyncio
import os
import subprocess
import tempfile
from typing import Any, Dict, List

from dstack._internal.core.errors import SSHError
from dstack._internal.core.services.ssh import get_ssh_error
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class AsyncSSHTunnel:
    def __init__(self, user_host: str, id_rsa: str, options: Dict[str, Any], args: List[str]):
        # TODO(egor-s): reuse existing SSH control sock (in case of server restart)
        self.user_host = user_host

        self._temp_dir = tempfile.TemporaryDirectory()
        with open(
            self.id_rsa, opener=lambda path, flags: os.open(path, flags, 0o600), mode="w"
        ) as f:
            f.write(id_rsa)

        self._start_cmd = ["ssh", "-F", "none", "-i", self.id_rsa, "-f", "-N"]
        self._start_cmd += ["-M", "-S", self.control_sock_path]
        for key, value in options.items():
            self._start_cmd += ["-o", f"{key}={value}"]
        self._start_cmd += args
        self._start_cmd += [user_host]
        self._start_cmd = self._interpolate(self._start_cmd)

        self._stop_cmd = ["ssh", "-S", self.control_sock_path, "-O", "exit", user_host]
        self._stop_cmd = self._interpolate(self._stop_cmd)

        self._check_cmd = ["ssh", "-S", self.control_sock_path, "-O", "check", user_host]
        self._check_cmd = self._interpolate(self._check_cmd)

        self._exec_cmd = ["ssh", "-S", self.control_sock_path, user_host]

    def _interpolate(self, cmd: List[str]) -> List[str]:
        data = {
            "temp_dir": self.temp_dir,
            "id_rsa": self.id_rsa,
            "control_sock_path": self.control_sock_path,
        }
        return [arg.format(**data) for arg in cmd]

    @property
    def temp_dir(self) -> str:
        return self._temp_dir.name

    @property
    def id_rsa(self) -> str:
        return os.path.join(self.temp_dir, "id_rsa")

    @property
    def control_sock_path(self) -> str:
        return os.path.join(self.temp_dir, "control")

    async def start(self):
        proc = await asyncio.create_subprocess_exec(
            *self._start_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            # TODO(egor-s): make robust, retry
            raise get_ssh_error(stderr)
        logger.debug("SSH tunnel `%s` is up", self.user_host)

    async def stop(self):
        proc = await asyncio.create_subprocess_exec(
            *self._stop_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        await proc.wait()

    async def check(self) -> bool:
        proc = await asyncio.create_subprocess_exec(
            *self._check_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        await proc.wait()
        ok = proc.returncode == 0
        # logger.debug("SSH tunnel %s check: %s", self.user_host, "OK" if ok else "FAIL")
        return ok

    async def exec(self, command: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            *self._exec_cmd, command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            # TODO(egor-s): make robust, retry
            raise SSHError(stderr.decode())
        return stdout.decode()
