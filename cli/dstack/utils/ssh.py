import os

from paramiko.config import SSHConfig

from dstack.utils.common import PathLike

ssh_config_path = os.path.expanduser("~/.ssh/config")


def get_host_config(hostname: str) -> dict:
    if os.path.exists(ssh_config_path):
        with open(ssh_config_path, "r") as f:
            config = SSHConfig()
            with open(ssh_config_path, "r") as f:
                config.parse(f)
            return config.lookup(hostname)
    return {}


def make_ssh_command_for_git(identity_file: PathLike) -> str:
    return f"ssh -o IdentitiesOnly=yes -F /dev/null -o IdentityFile={identity_file}"
