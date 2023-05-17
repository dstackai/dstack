from abc import ABC, abstractmethod
from typing import List

from dstack.core.app import AppSpec


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
    port = 2222

    @classmethod
    def patch_commands(cls, commands: List[str], *, ssh_pub_key: str = None, **kwargs):
        assert ssh_pub_key is not None
        commands.extend(
            [
                f'echo "{ssh_pub_key}" >> ~/.ssh/authorized_keys',
                f"ssh-keygen -A > /dev/null",
                f"/usr/sbin/sshd -p {cls.port}",
            ]
        )

    @classmethod
    def patch_apps(cls, apps: List[AppSpec], **kwargs):
        apps.append(AppSpec(port=cls.port, app_name="openssh-server"))
