import atexit
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

from dstack._internal.compat import IS_WINDOWS
from dstack._internal.core.errors import SSHError
from dstack._internal.core.models.instances import SSHConnectionParams
from dstack._internal.core.services.configs import ConfigManager
from dstack._internal.core.services.ssh.client import get_ssh_client_info
from dstack._internal.core.services.ssh.ports import PortsLock
from dstack._internal.core.services.ssh.tunnel import SSHTunnel, ports_to_forwarded_sockets
from dstack._internal.utils.path import FilePath, PathLike
from dstack._internal.utils.ssh import (
    include_ssh_config,
    normalize_path,
    update_ssh_config,
)


class SSHAttach:
    @classmethod
    def get_control_sock_path(cls, run_name: str) -> Path:
        return ConfigManager().dstack_ssh_dir / f"{run_name}.control.sock"

    @classmethod
    def reuse_ports_lock(cls, run_name: str) -> Optional[PortsLock]:
        if not get_ssh_client_info().supports_control_socket:
            raise SSHError("Unsupported SSH client")
        control_sock_path = normalize_path(cls.get_control_sock_path(run_name))
        filter_prefix: str
        output: bytes
        if IS_WINDOWS:
            filter_prefix = "powershell"
            # This script always returns zero exit status.
            output = subprocess.check_output(
                [
                    "powershell",
                    "-c",
                    f"""Get-CimInstance Win32_Process \
                        -filter "commandline like '%-S {control_sock_path}%'" \
                        | select -ExpandProperty CommandLine \
                    """,
                ]
            )
        else:
            filter_prefix = "grep"
            ps = subprocess.Popen(("ps", "-A", "-o", "command"), stdout=subprocess.PIPE)
            cp = subprocess.run(
                ["grep", "-F", "--", f"-S {control_sock_path}"],
                stdin=ps.stdout,
                stdout=subprocess.PIPE,
            )
            ps.wait()
            # From grep man page: "the exit status is 0 if a line is selected,
            # 1 if no lines were selected, and 2 if an error occurred".
            if cp.returncode == 1:
                return None
            if cp.returncode != 0:
                raise SSHError(
                    f"Unexpected grep exit status {cp.returncode} while searching for ssh process"
                )
            output = cp.stdout
        commands = list(
            filter(lambda s: not s.startswith(filter_prefix), output.decode().strip().split("\n"))
        )
        if commands:
            port_pattern = r"-L (?:[\w.-]+:)?(\d+):localhost:(\d+)"
            matches = re.findall(port_pattern, commands[0])
            return PortsLock(
                {int(target_port): int(local_port) for local_port, target_port in matches}
            )
        return None

    def __init__(
        self,
        hostname: str,
        ssh_port: int,
        user: str,
        id_rsa_path: PathLike,
        ports_lock: PortsLock,
        run_name: str,
        dockerized: bool,
        ssh_proxy: Optional[SSHConnectionParams] = None,
        local_backend: bool = False,
        bind_address: Optional[str] = None,
    ):
        self._ports_lock = ports_lock
        self.ports = ports_lock.dict()
        self.run_name = run_name
        self.ssh_config_path = ConfigManager().dstack_ssh_config_path
        control_sock_path = self.get_control_sock_path(run_name)
        # Cast all path-like values used in configs to FilePath instances for automatic
        # path normalization in :func:`update_ssh_config`.
        self.control_sock_path = FilePath(control_sock_path)
        self.identity_file = FilePath(id_rsa_path)
        self.tunnel = SSHTunnel(
            destination=run_name,
            identity=self.identity_file,
            forwarded_sockets=ports_to_forwarded_sockets(
                ports=self.ports,
                bind_local=bind_address or "localhost",
            ),
            control_sock_path=control_sock_path,
            ssh_config_path=self.ssh_config_path,
            options={
                "ExitOnForwardFailure": "yes",
            },
        )
        self.ssh_proxy = ssh_proxy
        if ssh_proxy is None:
            self.host_config = {
                "HostName": hostname,
                "Port": ssh_port,
                "User": user,
                "IdentityFile": self.identity_file,
                "IdentitiesOnly": "yes",
                "StrictHostKeyChecking": "no",
                "UserKnownHostsFile": "/dev/null",
            }
        else:
            self.host_config = {
                "HostName": ssh_proxy.hostname,
                "Port": ssh_proxy.port,
                "User": ssh_proxy.username,
                "IdentityFile": self.identity_file,
                "IdentitiesOnly": "yes",
                "StrictHostKeyChecking": "no",
                "UserKnownHostsFile": "/dev/null",
            }
        if dockerized and not local_backend:
            self.container_config = {
                "HostName": "localhost",
                "Port": 10022,
                "User": "root",  # TODO(#1535): support non-root images properly
                "IdentityFile": self.identity_file,
                "IdentitiesOnly": "yes",
                "StrictHostKeyChecking": "no",
                "UserKnownHostsFile": "/dev/null",
                "ProxyJump": f"{run_name}-host",
            }
        elif ssh_proxy is not None:
            self.container_config = {
                "HostName": hostname,
                "Port": ssh_port,
                "User": user,
                "IdentityFile": self.identity_file,
                "IdentitiesOnly": "yes",
                "StrictHostKeyChecking": "no",
                "UserKnownHostsFile": "/dev/null",
                "ProxyJump": f"{run_name}-jump-host",
            }
        else:
            self.container_config = None
        if self.container_config is not None and get_ssh_client_info().supports_multiplexing:
            self.container_config.update(
                {
                    "ControlMaster": "auto",
                    "ControlPath": self.control_sock_path,
                }
            )

    def attach(self):
        include_ssh_config(self.ssh_config_path)
        if self.container_config is None:
            update_ssh_config(self.ssh_config_path, self.run_name, self.host_config)
        elif self.ssh_proxy is not None:
            update_ssh_config(self.ssh_config_path, f"{self.run_name}-jump-host", self.host_config)
            update_ssh_config(self.ssh_config_path, self.run_name, self.container_config)
        else:
            update_ssh_config(self.ssh_config_path, f"{self.run_name}-host", self.host_config)
            update_ssh_config(self.ssh_config_path, self.run_name, self.container_config)

        max_retries = 10
        self._ports_lock.release()
        for i in range(max_retries):
            try:
                self.tunnel.open()
                atexit.register(self.detach)
                break
            except SSHError:
                if i < max_retries - 1:
                    time.sleep(1)
        else:
            self.detach()
            raise SSHError("Can't connect to the remote host")

    def detach(self):
        self.tunnel.close()
        update_ssh_config(self.ssh_config_path, f"{self.run_name}-jump-host", {})
        update_ssh_config(self.ssh_config_path, f"{self.run_name}-host", {})
        update_ssh_config(self.ssh_config_path, self.run_name, {})

    def __enter__(self):
        self.attach()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.detach()
