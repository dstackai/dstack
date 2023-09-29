import time

from dstack._internal.core.errors import SSHError
from dstack._internal.core.services.configs import ConfigManager
from dstack._internal.core.services.ssh.ports import PortsLock
from dstack._internal.core.services.ssh.tunnel import ClientTunnel
from dstack._internal.utils.path import PathLike
from dstack._internal.utils.ssh import (
    include_ssh_config,
    ssh_config_add_host,
    ssh_config_remove_host,
)


class SSHAttach:
    def __init__(
        self,
        hostname: str,
        ssh_port: int,
        user: str,
        id_rsa_path: PathLike,
        ports_lock: PortsLock,
        run_name: str,
        dockerized: bool,
    ):
        self._ports_lock = ports_lock
        self.ports = ports_lock.dict()
        self.run_name = run_name
        self.tunnel = ClientTunnel(run_name, self.ports, id_rsa_path=id_rsa_path)
        self.host_config = {
            "HostName": hostname,
            "Port": ssh_port,
            "User": user,
            "IdentityFile": id_rsa_path,
            "StrictHostKeyChecking": "no",
            "UserKnownHostsFile": "/dev/null",
        }
        if dockerized:
            self.container_config = {
                "HostName": "localhost",
                "Port": 10022,
                "User": "root",
                "IdentityFile": id_rsa_path,
                "StrictHostKeyChecking": "no",
                "UserKnownHostsFile": "/dev/null",
                "ControlPath": self.tunnel.control_sock_path,
                "ControlMaster": "auto",
                "ControlPersist": "yes",
                "ProxyJump": f"{run_name}-host",
            }
        else:
            self.container_config = None
        self.ssh_config_path = str(ConfigManager().dstack_ssh_config_path)

    def attach(self):
        include_ssh_config(self.ssh_config_path)
        if self.container_config is None:
            ssh_config_add_host(self.ssh_config_path, self.run_name, self.host_config)
        else:
            ssh_config_add_host(self.ssh_config_path, f"{self.run_name}-host", self.host_config)
            ssh_config_add_host(self.ssh_config_path, self.run_name, self.container_config)

        max_retries = 10
        self._ports_lock.release()
        for i in range(max_retries):
            try:
                self.tunnel.open()
                break
            except SSHError:
                if i < max_retries - 1:
                    time.sleep(1)
        else:
            self.detach()
            raise SSHError("Can't connect to the remote host")

    def detach(self):
        self.tunnel.close()
        ssh_config_remove_host(self.ssh_config_path, f"{self.run_name}-host")
        ssh_config_remove_host(self.ssh_config_path, self.run_name)

    def __enter__(self):
        self.attach()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.detach()
