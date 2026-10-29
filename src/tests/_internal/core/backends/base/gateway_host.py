import io
import re
import shlex
import tarfile
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Optional, cast

import pytest
from testcontainers.core.container import DockerContainer

from dstack._internal.core.backends.base.compute import _get_dstack_gateway_install_script
from dstack._internal.utils.common import get_or_error

GATEWAY_DIR = "/home/ubuntu/dstack"

_STUB_PATH = "/usr/local/bin/gateway-host-stub"
_EVENTS_PATH = "/tmp/gateway-host-events"

# A single stub dispatching on the name it is invoked by. Every call is logged to the events file.
# - python: a venv's interpreter. Reports the Python and dstack versions from the venv's
#   `installed` file to the gateway install script's version check.
# - uv: reports the version from its `uv.version` file, creates venvs, and fails on the
#   subcommand named in its `uv.fail_on` file.
# - wget: serves a uv release archive with the stub as uv, for the version in the URL.
# - uname: reports x86_64 regardless of the machine running the tests.
# - sudo: logs systemctl calls with the active venv at the time of the call, runs other commands.
_STUB = f"""\
#!/bin/sh
set -e
log() {{
  printf "%s\\n" "$*" >> {_EVENTS_PATH}
}}
case "${{0##*/}}" in
python)
  venv_path=${{0%/bin/python}}
  if [ "$1" = -c ]; then
    log "${{venv_path##*/}} python -c"
    exec cat "$venv_path/installed"
  fi
  log "${{venv_path##*/}} python $*"
  ;;
uv)
  log "uv $*"
  if [ -f "$0.fail_on" ] && [ "$1" = "$(cat "$0.fail_on")" ]; then
    exit 1
  fi
  case "$1" in
  --version)
    echo "uv $(cat "$0.version") (0123456 2026-01-01 x86_64-unknown-linux-musl)"
    ;;
  venv)
    for arg; do venv_path=$arg; done
    mkdir -p "$venv_path/bin"
    ln -s {_STUB_PATH} "$venv_path/bin/python"
    ;;
  esac
  ;;
wget)
  for arg; do url=$arg; done
  log "wget $url"
  version=${{url#*/download/}}
  asset=${{url##*/}}
  release=$(mktemp -d)
  mkdir "$release/${{asset%.tar.gz}}"
  ln -s {_STUB_PATH} "$release/${{asset%.tar.gz}}/uv"
  echo "${{version%%/*}}" > "$release/${{asset%.tar.gz}}/uv.version"
  tar -czf "$2" -C "$release" "${{asset%.tar.gz}}"
  ;;
uname)
  echo x86_64
  ;;
sudo)
  if [ "$1" = systemctl ]; then
    log "$* active=$(cat {GATEWAY_DIR}/version)"
  else
    exec "$@"
  fi
  ;;
esac
"""


def get_install_script_var(name: str) -> str:
    """
    Returns a variable pinned in the gateway install script, e.g. `python_version`.
    """
    match = re.search(rf"^{name}=(\S+)$", _get_dstack_gateway_install_script(), re.MULTILINE)
    assert match is not None
    return match.group(1)


@dataclass
class GatewayHostResult:
    returncode: int
    stdout: str
    stderr: str


class GatewayHost:
    """
    A gateway host emulated in a Docker container for running the gateway install command.

    The command runs for real in a shell, which covers quoting, version checks, and the order of
    venv switching and service restart. The commands that need the network, root, or systemd are
    stubbed: sudo, wget, uname, uv, and the venvs' python. Everything else, including `rm -rf`,
    runs as is.

    Stubs alone cannot contain the script: any command they don't cover would run on the machine
    running the tests, and a script change can add one without updating the stubs. The container
    bounds what such a change can touch. It also lets the script run unmodified against the real
    `/home/ubuntu/dstack` on the same Ubuntu image that gateways use.
    """

    def __init__(self, container: DockerContainer):
        self._container = container

    def add_venv(self, name: str, installed: Optional[str], active: bool = False):
        """
        Args:
            installed: `"<python_version> <dstack_version>"` reported by the venv's python.
                `None` emulates a broken venv.
        """
        venv_path = f"{GATEWAY_DIR}/{name}"
        script = f"mkdir -p {venv_path}/bin && ln -s {_STUB_PATH} {venv_path}/bin/python"
        if installed is not None:
            script += f" && echo {shlex.quote(installed)} > {venv_path}/installed"
        if active:
            script += f" && echo {name} > {GATEWAY_DIR}/version"
        self._exec(script)

    def add_uv(self, version: str, fail_on: Optional[str] = None):
        """
        Args:
            fail_on: The uv subcommand to fail, e.g. `"pip"`.
        """
        uv_path = f"{GATEWAY_DIR}/bin/uv"
        script = (
            f"mkdir -p {GATEWAY_DIR}/bin && ln -s {_STUB_PATH} {uv_path}"
            f" && echo {shlex.quote(version)} > {uv_path}.version"
        )
        if fail_on is not None:
            script += f" && echo {shlex.quote(fail_on)} > {uv_path}.fail_on"
        self._exec(script)

    def run(self, command: str) -> GatewayHostResult:
        result = self._container.get_wrapped_container().exec_run(
            ["sh", "-c", command], demux=True
        )
        # With demux=True, the output is a (stdout, stderr) pair
        stdout, stderr = cast(tuple[Optional[bytes], Optional[bytes]], result.output)
        return GatewayHostResult(
            returncode=get_or_error(result.exit_code),
            stdout=(stdout or b"").decode(),
            stderr=(stderr or b"").decode(),
        )

    def events(self) -> list[str]:
        return self._exec(f"cat {_EVENTS_PATH}").splitlines()

    def active_venv(self) -> str:
        return self._exec(f"cat {GATEWAY_DIR}/version").strip()

    def uv_version(self) -> str:
        return self._exec(f"cat {GATEWAY_DIR}/bin/uv.version").strip()

    def exists(self, path: str) -> bool:
        return self.run(f"test -e {shlex.quote(path)}").returncode == 0

    def reset(self):
        self._exec(f"rm -rf {GATEWAY_DIR} && : > {_EVENTS_PATH}")

    def _exec(self, script: str) -> str:
        result = self.run(script)
        assert result.returncode == 0, result.stderr
        return result.stdout


@pytest.fixture(scope="session")
def gateway_host_container() -> Iterator[DockerContainer]:
    # The same image as Kubernetes gateway pods. `init` lets the container stop without a timeout.
    with (
        DockerContainer("ubuntu:22.04")
        .with_command("sleep infinity")
        .with_kwargs(init=True) as container
    ):
        container.get_wrapped_container().put_archive("/", _get_stubs_archive())
        yield container


@pytest.fixture
def gateway_host(gateway_host_container: DockerContainer) -> GatewayHost:
    host = GatewayHost(gateway_host_container)
    host.reset()
    return host


def _get_stubs_archive() -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        stub = _STUB.encode()
        info = tarfile.TarInfo(_STUB_PATH.lstrip("/"))
        info.size = len(stub)
        info.mode = 0o755
        archive.addfile(info, io.BytesIO(stub))
        for command in ("sudo", "uname", "wget"):
            info = tarfile.TarInfo(f"usr/local/bin/{command}")
            info.type = tarfile.SYMTYPE
            info.linkname = _STUB_PATH
            archive.addfile(info)
    return buffer.getvalue()
