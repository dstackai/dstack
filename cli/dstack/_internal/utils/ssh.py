import os
import re
import subprocess
from pathlib import Path

from filelock import FileLock
from paramiko.config import SSHConfig

from dstack._internal.utils.common import PathLike

default_ssh_config_path = "~/.ssh/config"


def get_host_config(hostname: str, ssh_config_path: PathLike = default_ssh_config_path) -> dict:
    ssh_config_path = os.path.expanduser(ssh_config_path)
    if os.path.exists(ssh_config_path):
        config = SSHConfig.from_path(ssh_config_path)
        return config.lookup(hostname)
    return {}


def make_ssh_command_for_git(identity_file: PathLike) -> str:
    return f"ssh -o IdentitiesOnly=yes -F /dev/null -o IdentityFile={identity_file}"


def try_ssh_key_passphrase(identity_file: PathLike, passphrase: str = "") -> bool:
    r = subprocess.run(
        ["ssh-keygen", "-y", "-P", passphrase, "-f", identity_file],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return r.returncode == 0


def include_ssh_config(path: PathLike, ssh_config_path: PathLike = default_ssh_config_path):
    """
    Adds Include entry on top of the default ssh config file
    :param path: Absolute path to config
    :param ssh_config_path: ~/.ssh/config
    """
    ssh_config_path = os.path.expanduser(ssh_config_path)
    Path(ssh_config_path).parent.mkdir(0o600, parents=True, exist_ok=True)
    include = f"Include {path}\n"
    content = ""
    with FileLock(str(ssh_config_path) + ".lock"):
        if os.path.exists(ssh_config_path):
            with open(ssh_config_path, "r") as f:
                content = f.read()
        if include not in content:
            with open(ssh_config_path, "w") as f:
                f.write(include + content)


def ssh_config_add_host(path: PathLike, host: str, options: dict):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(path) + ".lock"):
        with open(path, "a") as f:
            f.write(f"Host {host}\n")
            for k, v in options.items():
                f.write(f"    {k} {v}\n")
            f.flush()


def ssh_config_remove_host(path: PathLike, host: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(path) + ".lock"):
        copy_mode = True
        content = ""
        if os.path.exists(path):
            with open(path, "r") as f:
                for line in f:
                    m = re.match(rf"^Host\s+(\S+)$", line.strip())
                    if m is not None:
                        copy_mode = m.group(1) != host
                    if copy_mode:
                        content += line
        with open(path, "w") as f:
            f.write(content)
