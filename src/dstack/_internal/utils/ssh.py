import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Optional, Union

import paramiko
from filelock import FileLock
from paramiko.config import SSHConfig
from paramiko.pkey import PKey, PublicBlob
from paramiko.ssh_exception import SSHException

from dstack._internal.compat import IS_WINDOWS
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import FilePath, PathLike

logger = get_logger(__name__)


default_ssh_config_path = "~/.ssh/config"

SUPPORTED_KEY_TYPES = (paramiko.RSAKey, paramiko.ECDSAKey, paramiko.Ed25519Key)


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
    # No need to use :func:`find_ssh_client()` even on Windows even if `ssh` not in
    # Windows `PATH` -- MSYS2 git (from Git for Windows) always has access to it,
    # see https://www.msys2.org/docs/environments/ ("MSYS environment [...] is always active")
    return (
        f'ssh -F none -i "{normalize_path(identity_file)}"'
        " -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o IdentitiesOnly=yes"
    )


def try_ssh_key_passphrase(identity_file: PathLike, passphrase: str = "") -> bool:
    ssh_keygen = find_ssh_util("ssh-keygen")
    if ssh_keygen is None:
        logger.warning("ssh-keygen not found")
        return False
    r = subprocess.run(
        [ssh_keygen, "-y", "-P", passphrase, "-f", identity_file],
        stdout=subprocess.DEVNULL,
        stderr=sys.stdout.buffer,
    )
    return r.returncode == 0


def normalize_path(path: PathLike, *, collapse_user: bool = False) -> str:
    """
    Converts a path to the most compatible format.
    On Windows, replaces backslashes with slashes.
    Additionally, if `collapse_user` is `True`, tries to replace the user home part of the path
    with `~`.

    :param path: Path object or string
    :param collapse_user: try to replace user home prefix with `~`. `False` by default.
    :return: Normalized path as string
    """
    if collapse_user:
        # The following "reverse" expanduser operation not only makes paths shorter and "nicer",
        # but also fixes one specific issue with OpenSSH bundled with Git for Windows (MSYS2),
        # see :func:`include_ssh_config` for details.
        try:
            path = Path(path).relative_to(Path.home())
            path = f"~/{path}"
        except ValueError:
            pass
    if IS_WINDOWS:
        # Git for Windows ssh (based on MSYS2, but there may be subtle differences between
        # vanilla MSYS2 ssh and Git for Windows ssh) supports:
        #   * C:\\Users\\User
        #   * C:/Users/User
        #   * /c/Users/User
        # does not support:
        #   * C:\Users\User (as pathllib.WindowsPath is rendered)
        # OpenSSH_for_Windows supports:
        #   * C:\Users\User
        #   * C:\\Users\\User
        #   * C:/Users/User
        # does not support:
        #   * /c/User/User
        # We use C:/Users/User format as the safest (supported by both ssh builds;
        # no backslash-escaping pitfalls)
        return str(path).replace("\\", "/")
    return str(path)


def include_ssh_config(path: PathLike, ssh_config_path: PathLike = default_ssh_config_path):
    """
    Adds Include entry on top of the default ssh config file
    :param path: Absolute path to config
    :param ssh_config_path: ~/.ssh/config
    """
    ssh_config_path = os.path.expanduser(ssh_config_path)
    Path(ssh_config_path).parent.mkdir(0o600, parents=True, exist_ok=True)
    # MSYS2 OpenSSH accepts only /c/Users/User/... format in the Include directive (although
    # it accepts C:/Users/User/... in other directives). We try to work around this issue
    # converting the path to ~/.dstack/... format.
    path = normalize_path(path, collapse_user=True)
    include = f"Include {path}\n"
    content = ""
    try:
        with FileLock(str(ssh_config_path) + ".lock"):
            if os.path.exists(ssh_config_path):
                with open(ssh_config_path, "r") as f:
                    content = f.read()
            if include not in content:
                with open(ssh_config_path, "w") as f:
                    f.write(include + content)
    except PermissionError:
        logger.warning(
            f"Couldn't update `{ssh_config_path}` due to a permissions problem.\n"
            f"The `vscode://vscode-remote/ssh-remote+<run name>/workflow` and "
            f"`cursor://vscode-remote/ssh-remote+<run name>/workflow` links and "
            f"the `ssh <run name>` command won't work.\n"
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


def update_ssh_config(path: PathLike, host: str, options: Dict[str, Union[str, int, FilePath]]):
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
                    if isinstance(v, FilePath):
                        v = normalize_path(v.path, collapse_user=True)
                    f.write(f"    {k} {v}\n")
            f.flush()


def convert_ssh_key_to_pem(private_string: str) -> str:
    if not private_string.startswith("-----BEGIN PRIVATE KEY-----"):
        return private_string

    with tempfile.NamedTemporaryFile(mode="w+") as key_file:
        key_file.write(private_string)
        key_file.flush()
        if ssh_keygen := find_ssh_util("ssh-keygen"):
            cmd = [ssh_keygen, "-p", "-m", "PEM", "-f", key_file.name, "-y", "-q", "-N", ""]
            try:
                subprocess.run(
                    cmd,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as e:
                logger.error("Fail to convert ssh key: stdout=%s, stderr=%s", e.stdout, e.stderr)
        else:
            logger.error("Use a PEM key or install ssh-keygen to convert it automatically")
        key_file.seek(0)
        private_string = key_file.read()
    return private_string


def pkey_from_str(private_string: str) -> PKey:
    for key_type in SUPPORTED_KEY_TYPES:
        try:
            key_file = io.StringIO(private_string.strip())
            pkey = key_type.from_private_key(key_file)
            key_file.close()
            return pkey
        except (SSHException, ValueError):
            pass

    raise ValueError("Unsupported key type")


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


def find_ssh_client() -> Optional[Path]:
    """
    Finds and returns an absolute path of `ssh` executable or `None` if not found.

    If the `DSTACK_SSH_CLIENT` environment variable is set, return its value, otherwise:
        * on POSIX, look for `ssh` executable in `PATH` and return it (if any).
        * on Windows, first look for OpenSSH bundled with Git for Windows checking
        a known directory structure, then check `PATH`, and finally check a well-known location of
        OpenSSH for Windows.
    """
    path_str = os.getenv("DSTACK_SSH_CLIENT")
    if path_str:
        path = Path(path_str)
        if path.exists():
            return path.resolve()
        logger.warning("DSTACK_SSH_CLIENT=%s does not exist", path_str)
        return None
    if not IS_WINDOWS:
        path_str = shutil.which("ssh")
        if path_str:
            return Path(path_str)
        return None
    # First, we check for ssh bundled with Git for Windows (MSYS2/MinGW-w64-built OpenSSH Portable)
    # as a preferred client. It supports ForkAfterAuthentication; ControlMaster is only partially
    # supported, we don't use it.
    git_path_str = shutil.which("git")
    if git_path_str:
        # C:\Program Files\Git\cmd\git.exe -> C:\Program Files\Git\usr\bin\ssh.exe
        path = Path(git_path_str).parent.parent / "usr" / "bin" / "ssh.exe"
        if path.exists():
            return path
    # Then we check for any ssh client in PATH. It can be anything, but most likely it will be
    # OpenSSH for Windows (see below). Nonetheless, it's worth trying since it's also may be
    # MSYS2/Cygwin OpenSSH Portable.
    path_str = shutil.which("ssh")
    if path_str:
        return Path(path_str)
    # Finally we check for OpenSSH for Windows (Microsoft's fork of OpenSSH Portable).
    # It does not support some features, namely ControlMaster and ForkAfterAuthentication.
    windir_str = os.getenv("WINDIR")
    if windir_str:
        path = Path(windir_str) / "System32" / "OpenSSH" / "ssh.exe"
        if path.exists():
            return path
    return None


_ssh_util_dir: Optional[Path] = None


def find_ssh_util(name: str) -> Optional[Path]:
    """
    Returns an absolute path of a given `ssh*` utility or `None` if not found.

    :param name: a utility binary name without `.exe` suffix, e.g., `ssh-keygen`, `ssh-copy-id`.
    :return: a Path object.
    """
    global _ssh_util_dir
    if _ssh_util_dir is None:
        ssh_client_path = find_ssh_client()
        if ssh_client_path is None:
            return None
        _ssh_util_dir = ssh_client_path.parent
    if IS_WINDOWS:
        name = f"{name}.exe"
    path = _ssh_util_dir / name
    if path.exists():
        return path
    return None
