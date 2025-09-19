import atexit
import dataclasses
import re
import time
from pathlib import Path
from typing import Optional, Union

import psutil

from dstack._internal.core.errors import ConfigurationError, SSHError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import SSHConnectionParams
from dstack._internal.core.models.runs import JobProvisioningData
from dstack._internal.core.services.configs import ConfigManager
from dstack._internal.core.services.ssh.client import get_ssh_client_info
from dstack._internal.core.services.ssh.ports import PortsLock
from dstack._internal.core.services.ssh.tunnel import SSHTunnel, ports_to_forwarded_sockets
from dstack._internal.utils.path import FilePath, PathLike
from dstack._internal.utils.ssh import (
    default_ssh_config_path,
    get_host_config,
    include_ssh_config,
    normalize_path,
    update_ssh_config,
)

# ssh -L option format: [bind_address:]port:host:hostport
_SSH_TUNNEL_REGEX = re.compile(r"(?:[\w.-]+:)?(?P<local_port>\d+):localhost:(?P<remote_port>\d+)")


HostConfigType = dict[str, Union[str, int, FilePath]]


class SSHProxyConfig:
    """Do nothing"""

    def update_host(self, host: HostConfigType):
        pass

    def apply_provisioning_data(self, provisioning_data: JobProvisioningData):
        pass


@dataclasses.dataclass
class SSHProxyJumpConfig(SSHProxyConfig):
    """Add ProxyJump to the given host configuration"""

    jump_host: str

    def update_host(self, host: HostConfigType):
        host["ProxyJump"] = self.jump_host


@dataclasses.dataclass
class SSHProxyCommandConfig(SSHProxyConfig):
    """Add ProxyCommand to the given host configuration"""

    command: str

    def update_host(self, host: HostConfigType):
        host["ProxyCommand"] = self.command


@dataclasses.dataclass(kw_only=True)
class SSHProxyAwsSSMConfig(SSHProxyConfig):
    """Add ProxyCommand to use AWS SSM"""

    profile: Optional[str] = None
    region: Optional[str] = None
    document_name: Optional[str] = None
    instance_id: Optional[str] = None
    instance_region: Optional[str] = None

    def update_host(self, host: HostConfigType):
        if self.instance_id:
            host["HostName"] = self.instance_id
        region = self.region if self.region else self.instance_region
        document = self.document_name if self.document_name else "AWS-StartSSHSession"
        args = [
            "aws",
            "ssm",
            "start-session",
            "--target",
            "%h",
            "--document-name",
            document,
            "--parameters",
            "portNumber=%p",
        ]
        if region:
            args.extend(["--region", region])
        if self.profile:
            args.extend(["--profile", self.profile])
        command = f"sh -c '{' '.join(map(str, args))}'"
        host["ProxyCommand"] = command

    def apply_provisioning_data(self, provisioning_data: JobProvisioningData):
        backend = provisioning_data.get_base_backend()
        if backend != BackendType.AWS:
            raise ConfigurationError(
                "attach.proxy.type=aws-ssm is supported only for the AWS backend"
            )
        self.instance_id = provisioning_data.instance_id
        self.instance_region = provisioning_data.region


class SSHAttach:
    @classmethod
    def get_control_sock_path(cls, run_name: str) -> Path:
        return ConfigManager().dstack_ssh_dir / f"%r@{run_name}.control.sock"

    @classmethod
    def reuse_ports_lock(cls, run_name: str) -> Optional[PortsLock]:
        ssh_client_info = get_ssh_client_info()
        if not ssh_client_info.supports_control_socket:
            raise SSHError("Unsupported SSH client")
        ssh_exe = str(ssh_client_info.path)
        control_sock_path = normalize_path(cls.get_control_sock_path(run_name))
        for process in psutil.process_iter(["cmdline"]):
            cmdline = process.info["cmdline"]
            if not (cmdline and cmdline[0] == ssh_exe and control_sock_path in cmdline):
                continue
            port_mapping: dict[int, int] = {}
            cmdline_iter = iter(cmdline)
            for arg in cmdline_iter:
                if arg != "-L" or not (next_arg := next(cmdline_iter, None)):
                    continue
                if match := _SSH_TUNNEL_REGEX.fullmatch(next_arg):
                    local_port, remote_port = match.group("local_port", "remote_port")
                    port_mapping[int(remote_port)] = int(local_port)
            return PortsLock(port_mapping)
        return None

    def __init__(
        self,
        hostname: str,
        ssh_port: int,
        container_ssh_port: int,
        user: str,
        container_user: str,
        id_rsa_path: PathLike,
        ports_lock: PortsLock,
        run_name: str,
        dockerized: bool,
        ssh_proxy: Optional[SSHConnectionParams] = None,
        service_port: Optional[int] = None,
        local_backend: bool = False,
        bind_address: Optional[str] = None,
        proxy_config: Optional[SSHProxyConfig] = None,
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
            destination=f"root@{run_name}",
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
        self.service_port = service_port

        hosts: dict[str, dict[str, Union[str, int, FilePath]]] = {}
        self.hosts = hosts

        if local_backend:
            hosts[run_name] = {
                "HostName": hostname,
                "Port": container_ssh_port,
                "User": container_user,
                "IdentityFile": self.identity_file,
                "IdentitiesOnly": "yes",
                "StrictHostKeyChecking": "no",
                "UserKnownHostsFile": "/dev/null",
            }
        elif dockerized:
            if ssh_proxy is not None:
                # SSH instance with jump host
                # dstack has no IdentityFile for jump host, it must be either preconfigured
                # in the ~/.ssh/config or loaded into ssh-agent
                hosts[f"{run_name}-jump-host"] = {
                    "HostName": ssh_proxy.hostname,
                    "Port": ssh_proxy.port,
                    "User": ssh_proxy.username,
                    "StrictHostKeyChecking": "no",
                    "UserKnownHostsFile": "/dev/null",
                }
                jump_host_config = get_host_config(ssh_proxy.hostname, default_ssh_config_path)
                jump_host_identity_files = jump_host_config.get("identityfile")
                if jump_host_identity_files:
                    hosts[f"{run_name}-jump-host"].update(
                        {
                            "IdentityFile": jump_host_identity_files[0],
                            "IdentitiesOnly": "yes",
                        }
                    )
                hosts[f"{run_name}-host"] = {
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
                # Regular SSH instance or VM-based cloud instance
                hosts[f"{run_name}-host"] = {
                    "HostName": hostname,
                    "Port": ssh_port,
                    "User": user,
                    "IdentityFile": self.identity_file,
                    "IdentitiesOnly": "yes",
                    "StrictHostKeyChecking": "no",
                    "UserKnownHostsFile": "/dev/null",
                }
            hosts[run_name] = {
                "HostName": "localhost",
                "Port": container_ssh_port,
                "User": container_user,
                "IdentityFile": self.identity_file,
                "IdentitiesOnly": "yes",
                "StrictHostKeyChecking": "no",
                "UserKnownHostsFile": "/dev/null",
                "ProxyJump": f"{run_name}-host",
            }
        else:
            if ssh_proxy is not None:
                # Kubernetes
                hosts[f"{run_name}-jump-host"] = {
                    "HostName": ssh_proxy.hostname,
                    "Port": ssh_proxy.port,
                    "User": ssh_proxy.username,
                    "IdentityFile": self.identity_file,
                    "IdentitiesOnly": "yes",
                    "StrictHostKeyChecking": "no",
                    "UserKnownHostsFile": "/dev/null",
                }
                hosts[run_name] = {
                    "HostName": hostname,
                    "Port": ssh_port,
                    "User": container_user,
                    "IdentityFile": self.identity_file,
                    "IdentitiesOnly": "yes",
                    "StrictHostKeyChecking": "no",
                    "UserKnownHostsFile": "/dev/null",
                    "ProxyJump": f"{run_name}-jump-host",
                }
            else:
                # Container-based backends
                hosts[run_name] = {
                    "HostName": hostname,
                    "Port": ssh_port,
                    "User": container_user,
                    "IdentityFile": self.identity_file,
                    "IdentitiesOnly": "yes",
                    "StrictHostKeyChecking": "no",
                    "UserKnownHostsFile": "/dev/null",
                }
        if get_ssh_client_info().supports_multiplexing:
            hosts[run_name].update(
                {
                    "ControlMaster": "auto",
                    "ControlPath": self.control_sock_path,
                }
            )

        if proxy_config:
            # Apply proxy configuration for the first hop connection
            first_hop_key: Optional[str] = None
            if f"{run_name}-jump-host" in hosts:
                first_hop_key = f"{run_name}-jump-host"
            elif f"{run_name}-host" in hosts:
                first_hop_key = f"{run_name}-host"
            else:
                first_hop_key = run_name

            proxy_config.update_host(hosts[first_hop_key])

    def attach(self):
        include_ssh_config(self.ssh_config_path)
        for host, options in self.hosts.items():
            update_ssh_config(self.ssh_config_path, host, options)

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
        for host in self.hosts:
            update_ssh_config(self.ssh_config_path, host, {})

    def __enter__(self):
        self.attach()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.detach()
