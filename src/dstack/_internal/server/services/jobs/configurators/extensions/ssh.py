from typing import List, Optional

from dstack._internal.core.models.runs import AppSpec
from dstack._internal.server.services.jobs.configurators.extensions.base import (
    get_required_commands,
)


class SSHd:
    def __init__(self, key_pub: str, *, port: int = 10022):
        self.key_pub = key_pub
        self.port = port
        self.map_to_port: Optional[int] = None

    def get_required_commands(self) -> List[str]:
        get_sshd_required_commands = get_required_commands(["sshd"])
        return get_sshd_required_commands()

    def get_setup_commands(self) -> List[str]:
        return [
            f'sed -i "s/.*PasswordAuthentication.*/PasswordAuthentication no/g" /etc/ssh/sshd_config',
            f'sed -i "s/PermitRootLogin yes/PermitRootLogin yes/g" /etc/ssh/sshd_config',
            f"mkdir -p /run/sshd ~/.ssh",
            f"chmod 700 ~/.ssh",
            f"touch ~/.ssh/authorized_keys",
            f"chmod 600 ~/.ssh/authorized_keys",
            f"rm -rf /etc/ssh/ssh_host_*",
            f'echo "{self.key_pub}" >> ~/.ssh/authorized_keys',
            f"env >> ~/.ssh/environment",
            f'echo "export PATH=$PATH" >> ~/.profile',
            f"ssh-keygen -A > /dev/null",
        ]

    def get_start_commands(self) -> List[str]:
        return [
            f"/usr/sbin/sshd -p {self.port} -o PermitUserEnvironment=yes",
        ]

    def get_app_spec(self) -> AppSpec:
        return AppSpec(port=self.port, map_to_port=self.map_to_port, app_name="openssh-server")
