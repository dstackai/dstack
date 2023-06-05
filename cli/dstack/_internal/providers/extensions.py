from abc import ABC, abstractmethod
from typing import List, Optional

from dstack._internal.core.app import AppSpec


class ProviderExtension(ABC):
    @classmethod
    @abstractmethod
    def patch_commands(cls, commands: List[str]):
        pass

    @classmethod
    @abstractmethod
    def patch_apps(cls, apps: List[AppSpec]):
        pass


class OpenSSHExtension(ProviderExtension):
    port = 10022

    @classmethod
    def patch_commands(cls, commands: List[str], *, ssh_key_pub: str = None, **kwargs):
        assert ssh_key_pub is not None, "No SSH key provided"
        commands.extend(
            [
                f'echo "{ssh_key_pub}" >> ~/.ssh/authorized_keys',
                f"ssh-keygen -A > /dev/null",
                f"/usr/sbin/sshd -p {cls.port}",
            ]
        )

    @classmethod
    def patch_apps(cls, apps: List[AppSpec], *, map_to_port: Optional[int] = None, **kwargs):
        apps.append(AppSpec(port=cls.port, map_to_port=map_to_port, app_name="openssh-server"))
