from abc import ABC, abstractmethod
from typing import List, Optional

import requests

from dstack._internal.core.app import AppSpec


class ProviderExtension(ABC):
    @classmethod
    @abstractmethod
    def patch_setup(cls, commands: List[str], **kwargs):
        pass

    @classmethod
    @abstractmethod
    def patch_commands(cls, commands: List[str], **kwargs):
        pass

    @classmethod
    @abstractmethod
    def patch_apps(cls, apps: List[AppSpec], **kwargs):
        pass


class OpenSSHExtension(ProviderExtension):
    port = 10022

    @classmethod
    def patch_setup(cls, commands: List[str], **kwargs):
        pass

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


class VSCodeDesktopServer(ProviderExtension):
    @staticmethod
    def get_tag_sha(version: Optional[str] = None) -> str:
        repo_api = "https://api.github.com/repos/microsoft/vscode"
        if version is None:  # get latest
            version = requests.get(f"{repo_api}/releases/latest").json()["tag_name"]
        obj = requests.get(f"{repo_api}/git/ref/tags/{version}").json()["object"]
        if obj["type"] == "commit":
            return obj["sha"]
        raise NotImplementedError()

    @classmethod
    def patch_setup(
        cls, commands: List[str], *, vscode_extensions: Optional[List[str]] = None, **kwargs
    ):
        commit = cls.get_tag_sha()
        url = f"https://update.code.visualstudio.com/commit:{commit}/server-linux-$arch/stable"
        archive = "vscode-server-linux-$arch.tar.gz"
        target = f'~/.vscode-server/bin/"{commit}"'
        commands.extend(
            [
                f'if [ $(uname -m) = "aarch64" ]; then arch="arm64"; else arch="x64"; fi',
                f"mkdir -p /tmp",
                f'wget -q --show-progress "{url}" -O "/tmp/{archive}"',
                f"mkdir -vp {target}",
                f'tar --no-same-owner -xz --strip-components=1 -C {target} -f "/tmp/{archive}"',
                f'rm "/tmp/{archive}"',
            ]
        )
        if vscode_extensions:
            extensions = " ".join(f'--install-extension "{name}"' for name in vscode_extensions)
            commands.append(f'PATH="$PATH":{target}/bin code-server {extensions}')

    @classmethod
    def patch_commands(cls, commands: List[str], **kwargs):
        pass

    @classmethod
    def patch_apps(cls, apps: List[AppSpec], **kwargs):
        pass
