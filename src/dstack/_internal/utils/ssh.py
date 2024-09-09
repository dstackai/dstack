import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import paramiko
from filelock import FileLock
from paramiko.config import SSHConfig
from paramiko.pkey import PKey, PublicBlob
from paramiko.ssh_exception import SSHException

from dstack._internal.compat import IS_WINDOWS
from dstack._internal.core.errors import SSHError
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
    return f"ssh -F none -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o IdentitiesOnly=yes -F /dev/null -o IdentityFile={identity_file}"


def try_ssh_key_passphrase(identity_file: PathLike, passphrase: str = "") -> bool:
    r = subprocess.run(
        ["ssh-keygen", "-y", "-P", passphrase, "-f", identity_file],
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


def update_ssh_config(path: PathLike, host: str, options: Dict[str, Union[str, FilePath]]):
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
    path_str = os.getenv("DSTACK_SSH_CLIENT")
    if path_str:
        return Path(path_str)
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
    # Then we check for OpenSSH for Windows (Microsoft's fork of OpenSSH Portable).
    # It does not support some features, namely ControlMaster and ForkAfterAuthentication.
    windir_str = os.getenv("WINDIR")
    if windir_str:
        path = Path(windir_str) / "System32" / "OpenSSH" / "ssh.exe"
        if path.exists():
            return path
    # Finally, we check for any ssh client in PATH. It can be anything, it can be not compatible,
    # so we use it only as a last resort.
    path_str = shutil.which("ssh")
    if path_str:
        return Path(path_str)
    return None


@dataclass
class SSHClientInfo:
    # Path to `ssh` executable
    path: Path
    # Full version including portable suffix, e.g., "9.6p1"
    version: str
    # Base version not including portable suffix, e.g., (9, 6)
    version_tuple: Tuple[int, ...]
    # True if OpenSSH_for_Windows (Microsoft's OpenSSH Portable fork)
    for_windows: bool
    # Supports Control{Master,Path,Persist} directives, but only for control purposes
    # (e.g., `ssh -O exit`), cannot be used for connection multiplexing
    supports_control_socket: bool
    # Supports Control{Master,Path,Persist} for connection multiplexing
    supports_multiplexing: bool
    # Supports ForkAfterAuthentication (`ssh -f`)
    supports_background_mode: bool

    RAW_VERSION_REGEX = re.compile(
        r"OpenSSH_(?P<for_windows>for_Windows_)?(?P<base_version>[\d.]+)(?P<portable_version>p\d+)?",
        flags=re.I,
    )

    @classmethod
    def from_raw_version(cls, raw_version: str, path: Path) -> "SSHClientInfo":
        match = cls.RAW_VERSION_REGEX.match(raw_version)
        if not match:
            raise ValueError("no match")
        for_windows, base_version, portable_version = match.group(
            "for_windows", "base_version", "portable_version"
        )
        if portable_version:
            version = f"{base_version}{portable_version}"
        else:
            version = base_version
        return cls(
            path=path,
            version=version,
            version_tuple=tuple(map(int, base_version.split("."))),
            for_windows=bool(for_windows),
            supports_control_socket=(not for_windows),
            supports_multiplexing=(not IS_WINDOWS),
            supports_background_mode=(not for_windows),
        )


def inspect_ssh_client(path: PathLike) -> SSHClientInfo:
    """
    Inspects various aspects of a given SSH client — version, "flavor", features — by executing
    and parsing `ssh -V`.

    :param path: a path of the ssh executable.
    :return: :class:`SSHClientInfo` named tuple.
    :raise dstack._internal.core.errors.SSHError: if path does not exist, `ssh -V` returns
        non-zero exit status, or `ssh -V` output does not match the pattern.
    """
    path = Path(path).resolve()
    try:
        cp = subprocess.run(
            [path, "-V"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise SSHError(f"failed to execute `{path} -V`: {e}") from e
    output = cp.stderr
    if cp.returncode != 0:
        raise SSHError(f"`{path} -V` returned non-zero exit status {cp.returncode}: {output}")
    try:
        return SSHClientInfo.from_raw_version(output, path)
    except ValueError:
        raise SSHError(f"failed to parse `{path} -V` output: {output}")


_ssh_client_info: Optional[SSHClientInfo] = None


def get_ssh_client_info() -> SSHClientInfo:
    """
    Returns :class:`SSHClientInfo` for the default SSH client. The result is cached.

    :return: :class:`SSHClientInfo` named tuple.
    :raise dstack._internal.core.errors.SSHError: if no ssh client found or the underlying
    :func:`inspect_ssh_client` raises an error.
    """
    global _ssh_client_info
    if _ssh_client_info is not None:
        return _ssh_client_info
    path = find_ssh_client()
    if path is None:
        if IS_WINDOWS:
            msg = "SSH client not found, install Git for Windows."
        else:
            msg = "SSH client not found."
        raise SSHError(msg)
    _ssh_client_info = inspect_ssh_client(path)
    if _ssh_client_info.for_windows:
        raise SSHError("OpenSSH for Windows is not supported, install Git for Windows.")
    return _ssh_client_info
