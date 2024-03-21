import atexit
import re
import subprocess
import time
from typing import Optional, Tuple

from dstack._internal.core.errors import SSHError
from dstack._internal.core.models.instances import SSHConnectionParams
from dstack._internal.core.services.configs import ConfigManager
from dstack._internal.core.services.ssh.ports import PortsLock
from dstack._internal.core.services.ssh.tunnel import ClientTunnel
from dstack._internal.utils.path import PathLike
from dstack._internal.utils.ssh import get_ssh_config, include_ssh_config, update_ssh_config


class SSHAttach:
    @staticmethod
    def reuse_control_sock_path_and_port_locks(run_name: str) -> Optional[Tuple[str, PortsLock]]:
        ssh_config_path = str(ConfigManager().dstack_ssh_config_path)
        host_config = get_ssh_config(ssh_config_path, run_name)
        if host_config and host_config.get("ControlPath"):
            ps = subprocess.Popen(("ps", "-A", "-o", "command"), stdout=subprocess.PIPE)
            control_sock_path = host_config.get("ControlPath")
            output = subprocess.check_output(("grep", control_sock_path), stdin=ps.stdout)
            ps.wait()
            commands = list(
                filter(lambda s: not s.startswith("grep"), output.decode().strip().split("\n"))
            )
            if commands:
                port_pattern = r"-L (\d+):localhost:(\d+)"
                matches = re.findall(port_pattern, commands[0])
                return control_sock_path, PortsLock(
                    {int(local_port): int(target_port) for local_port, target_port in matches}
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
        control_sock_path: Optional[str] = None,
        local_backend: bool = False,
    ):
        self._ports_lock = ports_lock
        self.ports = ports_lock.dict()
        self.run_name = run_name
        self.ssh_config_path = str(ConfigManager().dstack_ssh_config_path)
        self.tunnel = ClientTunnel(
            run_name,
            self.ports,
            id_rsa_path=id_rsa_path,
            control_sock_path=control_sock_path,
            ssh_config_path=self.ssh_config_path,
        )
        self.ssh_proxy = ssh_proxy
        if ssh_proxy is None:
            self.host_config = {
                "HostName": hostname,
                "Port": ssh_port,
                "User": user,
                "IdentityFile": id_rsa_path,
                "IdentitiesOnly": "yes",
                "StrictHostKeyChecking": "no",
                "UserKnownHostsFile": "/dev/null",
            }
        else:
            self.host_config = {
                "HostName": ssh_proxy.hostname,
                "Port": ssh_proxy.port,
                "User": ssh_proxy.username,
                "IdentityFile": id_rsa_path,
                "IdentitiesOnly": "yes",
                "StrictHostKeyChecking": "no",
                "UserKnownHostsFile": "/dev/null",
            }
        if dockerized and not local_backend:
            self.container_config = {
                "HostName": "localhost",
                "Port": 10022,
                "User": "root",
                "IdentityFile": id_rsa_path,
                "IdentitiesOnly": "yes",
                "StrictHostKeyChecking": "no",
                "UserKnownHostsFile": "/dev/null",
                "ControlPath": self.tunnel.control_sock_path,
                "ControlMaster": "auto",
                "ControlPersist": "yes",
                "ProxyJump": f"{run_name}-host",
            }
        elif ssh_proxy is not None:
            self.container_config = {
                "HostName": hostname,
                "Port": ssh_port,
                "User": user,
                "IdentityFile": id_rsa_path,
                "IdentitiesOnly": "yes",
                "StrictHostKeyChecking": "no",
                "UserKnownHostsFile": "/dev/null",
                "ControlPath": self.tunnel.control_sock_path,
                "ControlMaster": "auto",
                "ControlPersist": "yes",
                "ProxyJump": f"{run_name}-jump-host",
            }
        else:
            self.container_config = None

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
