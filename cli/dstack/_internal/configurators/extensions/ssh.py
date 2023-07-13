from typing import List, Optional

from dstack._internal.core.app import AppSpec


class SSHd:
    def __init__(self, key_pub: str, *, port: int = 10022):
        self.key_pub = key_pub
        self.port = port
        self.map_to_port: Optional[int] = None

    def set_permissions(self, commands: List[str]):
        commands.extend(
            [
                f'sed -i "s/.*PasswordAuthentication.*/PasswordAuthentication no/g" /etc/ssh/sshd_config',
                f"mkdir -p /run/sshd ~/.ssh",
                f"chmod 700 ~/.ssh",
                f"touch ~/.ssh/authorized_keys",
                f"chmod 600 ~/.ssh/authorized_keys",
                f"rm -rf /etc/ssh/ssh_host_*",
            ]
        )

    def start(self, commands: List[str]):
        commands.extend(
            [
                f'echo "{self.key_pub}" >> ~/.ssh/authorized_keys',
                f"env >> ~/.ssh/environment",
                f'echo "export PATH=$PATH" >> ~/.profile',
                f"ssh-keygen -A > /dev/null",
                f"/usr/sbin/sshd -p {self.port} -o PermitUserEnvironment=yes",
            ]
        )

    def add_app(self, apps: List[AppSpec]):
        apps.append(
            AppSpec(port=self.port, map_to_port=self.map_to_port, app_name="openssh-server")
        )
