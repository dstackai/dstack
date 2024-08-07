import io
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Optional

import paramiko
from filelock import FileLock
from paramiko.config import SSHConfig
from paramiko.pkey import PKey, PublicBlob

from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import PathLike

logger = get_logger(__name__)


default_ssh_config_path = "~/.ssh/config"


def get_public_key_fingerprint(text: str) -> str:
    pb = PublicBlob.from_string(text)
    pk = PKey.from_type_string(pb.key_type, pb.key_blob)
    return pk.fingerprint


def get_host_config(hostname: str, ssh_config_path: PathLike = default_ssh_config_path) -> dict:
    ssh_config_path = os.path.expanduser(ssh_config_path)
    if os.path.exists(ssh_config_path):
        config = SSHConfig.from_path(ssh_config_path)
        return config.lookup(hostname)
    return {}


def make_ssh_command_for_git(identity_file: PathLike) -> str:
    return f"ssh -F none -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o IdentitiesOnly=yes -F /dev/null -o IdentityFile={identity_file}"


def try_ssh_key_passphrase(identity_file: PathLike, passphrase: str = "") -> bool:
    r = subprocess.run(
        ["ssh-keygen", "-y", "-P", passphrase, "-f", identity_file],
        stdout=subprocess.DEVNULL,
        stderr=sys.stdout.buffer,
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
            try:
                with open(ssh_config_path, "w") as f:
                    f.write(include + content)
            except PermissionError:
                logger.warning(
                    f"Couldn't update `{ssh_config_path}` due to a permissions problem.\n\n"
                    f"The `vscode://vscode-remote/ssh-remote+<run name>/workflow` link and "
                    f"the `ssh <run name>` command won't work.\n\n"
                    f"To fix this, make sure `{ssh_config_path}` is writable, or add "
                    f"`Include {path}` to the top of `{ssh_config_path}` manually.",
                    extra={"markup": True},
                )


def get_ssh_config(path: PathLike, host: str) -> Optional[Dict[str, str]]:
    if os.path.exists(path):
        config = {}
        current_host = None

        with open(path, "r") as f:
            for line in f:
                line = line.strip()

                if not line or line.startswith("#"):
                    continue

                if line.startswith("Host "):
                    current_host = line.split(" ")[1]
                    config[current_host] = {}
                else:
                    key, value = line.split(maxsplit=1)
                    config[current_host][key] = value
        return config.get(host)
    else:
        return None


def update_ssh_config(path: PathLike, host: str, options: Dict[str, str]):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(path) + ".lock"):
        copy_mode = True
        content = ""
        if os.path.exists(path):
            with open(path, "r") as f:
                for line in f:
                    m = re.match(r"^Host\s+(\S+)$", line.strip())
                    if m is not None:
                        copy_mode = m.group(1) != host
                    if copy_mode:
                        content += line
        with open(path, "w") as f:
            f.write(content)
            if options:
                f.write(f"Host {host}\n")
                for k, v in options.items():
                    f.write(f"    {k} {v}\n")
            f.flush()


def convert_pkcs8_to_pem(private_string: str) -> str:
    if not private_string.startswith("-----BEGIN PRIVATE KEY-----"):
        return private_string

    with tempfile.NamedTemporaryFile(mode="w+") as key_file:
        key_file.write(private_string)
        key_file.flush()
        cmd = ["ssh-keygen", "-p", "-m", "PEM", "-f", key_file.name, "-y", "-q", "-N", ""]
        try:
            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            logger.error("Use a PEM key or install ssh-keygen to convert it automatically")
        except subprocess.CalledProcessError as e:
            logger.error("Fail to convert ssh key: stdout=%s, stderr=%s", e.stdout, e.stderr)

        key_file.seek(0)
        private_string = key_file.read()
    return private_string


def rsa_pkey_from_str(private_string: str) -> PKey:
    key_file = io.StringIO(private_string.strip())
    pkey = paramiko.RSAKey.from_private_key(key_file)
    key_file.close()
    return pkey


def generate_public_key(private_key: PKey) -> str:
    public_key = f"{private_key.get_name()} {private_key.get_base64()}"
    return public_key


def check_required_ssh_version() -> bool:
    try:
        result = subprocess.run(["ssh", "-V"], capture_output=True, text=True)
    except subprocess.CalledProcessError:
        logger.error("Failed to get ssh version information")
    else:
        if result.returncode == 0:
            # Extract the version number from stderr in unix-like and window systems
            version_output = result.stderr if result.stderr.strip() else result.stdout.strip()

            match = re.search(r"_(\d+\.\d+)", version_output)
            if match:
                ssh_version = float(match.group(1))
                if ssh_version >= 8.4:
                    return True
                else:
                    return False

    return False
