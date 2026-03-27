import atexit
import re
import time
from pathlib import Path
from typing import Optional, Union

import psutil

from dstack._internal.core.errors import SSHError
from dstack._internal.core.models.instances import SSHConnectionParams
from dstack._internal.core.services.configs import ConfigManager
from dstack._internal.core.services.ssh.client import get_ssh_client_info
from dstack._internal.core.services.ssh.ports import PortsLock
from dstack._internal.core.services.ssh.tunnel import SSHTunnel, ports_to_forwarded_sockets
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import FilePath, PathLike
from dstack._internal.utils.ssh import (
    default_ssh_config_path,
    get_host_config,
    include_ssh_config,
    normalize_path,
    update_ssh_config,
)

logger = get_logger(__name__)

# ssh -L option format: [bind_address:]port:host:hostport
_SSH_TUNNEL_REGEX = re.compile(r"(?:[\w.-]+:)?(?P<local_port>\d+):localhost:(?P<remote_port>\d+)")


class BaseSSHAttach:
    """
    A base class for SSH attach implementations.

    Child classes must populate `self.hosts` inside overridden `__init__()` with at least one host
    named as a `run_name` argument value.
    """

    @classmethod
    def get_control_sock_path(cls, run_name: str) -> Path:
        return ConfigManager().dstack_ssh_dir / f"{run_name}.control.sock"

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
        *,
        run_name: str,
        identity_path: PathLike,
        ports_lock: PortsLock,
        destination: str,
        service_port: Optional[int] = None,
        bind_address: Optional[str] = None,
    ):
        self._attached = False
        self._hosts_added_to_ssh_config = False
        self._ports_lock = ports_lock
        self.ports = ports_lock.dict()
        self.run_name = run_name
        self.ssh_config_path = ConfigManager().dstack_ssh_config_path
        control_sock_path = self.get_control_sock_path(run_name)
        # Cast all path-like values used in configs to FilePath instances for automatic
        # path normalization in :func:`update_ssh_config`.
        self.control_sock_path = FilePath(control_sock_path)
        self.identity_file = FilePath(identity_path)
        self.tunnel = SSHTunnel(
            destination=destination,
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
        self.service_port = service_port
        self.hosts: dict[str, dict[str, Union[str, int, FilePath]]] = {}

    def __enter__(self):
        self.attach()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.detach()

    def attach(self):
        include_ssh_config(self.ssh_config_path)
        self._add_hosts_to_ssh_config()

        self._ports_lock.release()

        max_retries = 10
        for i in range(max_retries):
            try:
                self.tunnel.open()
                self._attached = True
                atexit.register(self.detach)
                return
            except SSHError:
                if i < max_retries - 1:
                    time.sleep(1)
        self._remove_hosts_from_ssh_config()
        raise SSHError("Can't connect to the remote host")

    def detach(self):
        self._remove_hosts_from_ssh_config()
        if not self._attached:
            logger.debug("Not attached")
            return
        self.tunnel.close()
        self._attached = False
        logger.debug("Detached")

    def _add_hosts_to_ssh_config(self):
        if self._hosts_added_to_ssh_config:
            return
        for host, options in self.hosts.items():
            update_ssh_config(self.ssh_config_path, host, options)
        self._hosts_added_to_ssh_config = True

    def _remove_hosts_from_ssh_config(self):
        if not self._hosts_added_to_ssh_config:
            return
        for host in self.hosts:
            update_ssh_config(self.ssh_config_path, host, {})
        self._hosts_added_to_ssh_config = False


class SSHAttach(BaseSSHAttach):
    """
    `SSHAttach` attaches to a job directly, via a backend-specific chain of hosts.

    Used when `dstack-sshproxy` is not configured on the server.
    """

    def __init__(
        self,
        *,
        run_name: str,
        identity_path: PathLike,
        ports_lock: PortsLock,
        hostname: str,
        ssh_port: int,
        container_ssh_port: int,
        user: str,
        container_user: str,
        dockerized: bool,
        ssh_proxy: Optional[SSHConnectionParams] = None,
        local_backend: bool = False,
        service_port: Optional[int] = None,
        bind_address: Optional[str] = None,
    ):
        super().__init__(
            run_name=run_name,
            identity_path=identity_path,
            ports_lock=ports_lock,
            destination=f"root@{run_name}",
            service_port=service_port,
            bind_address=bind_address,
        )
        hosts = self.hosts
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


class SSHProxyAttach(BaseSSHAttach):
    """
    `SSHProxyAttach` attaches to a job via `dstack-sshproxy`.

    Used when `dstack-sshproxy` is configured on the server.
    """

    def __init__(
        self,
        *,
        run_name: str,
        identity_path: PathLike,
        ports_lock: PortsLock,
        hostname: str,
        upstream_id: str,
        port: Optional[int] = None,
        service_port: Optional[int] = None,
        bind_address: Optional[str] = None,
    ):
        super().__init__(
            run_name=run_name,
            identity_path=identity_path,
            ports_lock=ports_lock,
            destination=f"{upstream_id}_root@{run_name}",
            service_port=service_port,
            bind_address=bind_address,
        )
        self.hosts[run_name] = {
            "HostName": hostname,
            "Port": port or 22,
            "User": upstream_id,
            "IdentityFile": self.identity_file,
            "IdentitiesOnly": "yes",
        }
