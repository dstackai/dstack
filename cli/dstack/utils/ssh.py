import os

from paramiko.config import SSHConfig

ssh_config_path = os.path.expanduser("~/.ssh/config")


def get_host_config(hostname: str) -> dict:
    if os.path.exists(ssh_config_path):
        with open(ssh_config_path, "r") as f:
            config = SSHConfig()
            with open(ssh_config_path, "r") as f:
                config.parse(f)
            return config.lookup(hostname)
    return {}
