"""The agent's working directory: aliasing, wrappers, and bundled skills."""

import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dstack._internal.cli.services.presets.session import (
    _CONSTRAINTS_FILENAME,
    _FINAL_REPORT_FILENAME,
    _PROGRESS_FILENAME,
    _RUNS_FILENAME,
    _TRIALS_FILENAME,
    PresetAgentSession,
)
from dstack._internal.compat import IS_WINDOWS
from dstack._internal.core.errors import CLIError

_SKILL_NAMES = ("dstack", "dstack-prototyping")
_PROGRESS_ENV = "DSTACK_PRESET_PROGRESS_LOG"
_MAX_RUN_NAME_LENGTH = 41
_MAX_UNIX_SOCKET_PATH_BYTES = 103


@dataclass(frozen=True)
class PresetAgentWorkspace:
    path: Path
    dstack_home: Path

    @property
    def temp_path(self) -> Path:
        return self.path / ".tmp"

    @property
    def bin_path(self) -> Path:
        return self.path / "bin"

    @property
    def progress_path(self) -> Path:
        return self.path / _PROGRESS_FILENAME

    @property
    def runs_path(self) -> Path:
        return self.path / _RUNS_FILENAME

    @property
    def trials_path(self) -> Path:
        return self.path / _TRIALS_FILENAME

    @property
    def constraints_path(self) -> Path:
        return self.path / _CONSTRAINTS_FILENAME

    @property
    def final_report_path(self) -> Path:
        return self.path / _FINAL_REPORT_FILENAME

    @property
    def agent_stdout_path(self) -> Path:
        return self.path / ".agent-stdout.jsonl"

    @property
    def agent_stderr_path(self) -> Path:
        return self.path / ".agent-stderr.log"


def create_agent_workspace(session: PresetAgentSession) -> PresetAgentWorkspace:
    real = session.path / "workspace"
    try:
        real.mkdir(mode=0o700)
        if IS_WINDOWS:
            # Windows has no Unix-socket path limit and symlinks require
            # privileges, so the workspace is used directly.
            alias = real
        else:
            alias = _create_workspace_alias(real)
            _validate_control_socket_path(alias)
        workspace = PresetAgentWorkspace(path=alias / "w", dstack_home=alias / "h")
        _prepare_workspace(workspace)
    except OSError as e:
        raise CLIError(f"Could not create the agent workspace under {real}: {e}") from e
    session.update_manifest(workspace=str(real), alias=str(alias))
    return workspace


def attach_agent_workspace(session: PresetAgentSession) -> PresetAgentWorkspace:
    manifest = session.read_manifest()
    real_value, alias_value = manifest.get("workspace"), manifest.get("alias")
    if not real_value or not alias_value:
        raise CLIError("The preset creation has no workspace to resume")
    real, alias = Path(real_value), Path(alias_value)
    if not real.is_dir():
        raise CLIError(
            f"The preset creation workspace no longer exists: {real}. "
            "Stop any leftover runs manually and create a new preset."
        )
    if alias != real:
        _ensure_workspace_alias(alias, real)
    return PresetAgentWorkspace(path=alias / "w", dstack_home=alias / "h")


def remove_agent_workspace(session: PresetAgentSession) -> None:
    manifest = session.read_manifest()
    alias = manifest.get("alias")
    workspace = manifest.get("workspace")
    if alias and alias != workspace and Path(alias).is_symlink():
        with suppress(OSError):
            os.unlink(alias)
    if workspace:
        shutil.rmtree(workspace, ignore_errors=True)


def scrub_workspace_token(session: PresetAgentSession) -> None:
    """Removes the agent's dstack config (a live token) from a workspace kept
    for resume, so an interrupted session leaves no credential on disk. Resume
    re-mints it via `build_preset_agent_env`."""
    workspace = session.read_manifest().get("workspace")
    if not workspace:
        return
    with suppress(OSError):
        (Path(workspace) / "h" / ".dstack" / "config.yml").unlink()


def _create_workspace_alias(real: Path) -> Path:
    base = _get_short_temp_dir() or tempfile.gettempdir()
    while True:
        alias = Path(base) / f"dpe-{secrets.token_hex(4)}"
        try:
            os.symlink(real, alias)
        except FileExistsError:
            continue
        return alias


def _ensure_workspace_alias(alias: Path, real: Path) -> None:
    if os.path.lexists(alias):
        if (
            alias.is_symlink()
            and os.readlink(alias) == str(real)
            and (IS_WINDOWS or os.lstat(alias).st_uid == os.getuid())
        ):
            return
        raise CLIError(
            f"The workspace alias path cannot be used safely: {alias}. "
            "Remove it manually if it is yours, or start a new session."
        )
    os.symlink(real, alias)


def _validate_control_socket_path(build_root: Path) -> None:
    if IS_WINDOWS:
        return
    path = build_root / "h" / ".dstack" / "ssh" / f"{'x' * _MAX_RUN_NAME_LENGTH}.control.sock"
    if len(os.fsencode(path)) > _MAX_UNIX_SOCKET_PATH_BYTES:
        raise CLIError(f"Temporary path is too long for an SSH control socket: {build_root}")


def _prepare_workspace(workspace: PresetAgentWorkspace) -> None:
    workspace.path.mkdir(mode=0o700, parents=True, exist_ok=False)
    workspace.dstack_home.mkdir(mode=0o700)
    workspace.temp_path.mkdir(mode=0o700)
    for path in [
        workspace.progress_path,
        workspace.runs_path,
        workspace.trials_path,
    ]:
        path.touch()
    workspace.bin_path.mkdir()
    _install_python_command(workspace.bin_path, "progress", _get_progress_script())
    (workspace.dstack_home / ".ssh").mkdir(mode=0o700)
    _install_dstack_wrapper(workspace.bin_path, workspace.dstack_home)
    _install_home_wrapper(workspace.bin_path, "ssh", workspace.dstack_home)
    _install_skills(workspace.path)


def _install_dstack_wrapper(bin_dir: Path, home: Path) -> None:
    script = f"""#!{sys.executable}
import os
import sys

from dstack._internal.cli.main import main

os.environ["HOME"] = {json.dumps(str(home))}
if os.name == "nt":
    os.environ["USERPROFILE"] = {json.dumps(str(home))}
sys.argv[0] = "dstack"
raise SystemExit(main())
"""
    _install_python_command(bin_dir, "dstack", script)


def _install_home_wrapper(bin_dir: Path, command: str, home: Path) -> None:
    executable = shutil.which(command)
    if executable is None:
        script = f"""#!{sys.executable}
import sys

print("Preset creation could not find the {command} executable.", file=sys.stderr)
raise SystemExit(127)
"""
    else:
        script = f"""#!{sys.executable}
import os
import subprocess
import sys

os.environ["HOME"] = {json.dumps(str(home))}
if os.name == "nt":
    os.environ["USERPROFILE"] = {json.dumps(str(home))}
raise SystemExit(subprocess.call([{json.dumps(executable)}, *sys.argv[1:]]))
"""
    _install_python_command(bin_dir, command, script)


def _install_python_command(bin_dir: Path, name: str, script: str) -> None:
    if not IS_WINDOWS:
        path = bin_dir / name
        path.write_text(script, encoding="utf-8")
        path.chmod(0o755)
        return

    # Avoid shadowing packages with the same name when Python adds this directory to sys.path.
    script_path = bin_dir / f"_{name}.py"
    script_path.write_text(script, encoding="utf-8")
    command = subprocess.list2cmdline([sys.executable, str(script_path)])
    (bin_dir / f"{name}.cmd").write_text(
        f"@echo off\n{command} %*\n",
        encoding="utf-8",
    )


def _get_short_temp_dir() -> Optional[str]:
    # Keep SSH control sockets below the Unix-domain socket path limit on macOS.
    if IS_WINDOWS:
        return None
    return "/tmp" if Path("/tmp").is_dir() else None


def _get_progress_script() -> str:
    return f"""#!{sys.executable}
import json
import os
from pathlib import Path
import sys

message = " ".join(sys.argv[1:]).strip()
if not message and not sys.stdin.isatty():
    message = sys.stdin.read().strip()
if not message:
    print("Usage: progress <message>", file=sys.stderr)
    raise SystemExit(2)
path = Path(os.environ.get("{_PROGRESS_ENV}", "{_PROGRESS_FILENAME}"))
with path.open("a", encoding="utf-8") as f:
    f.write(json.dumps({{"message": message}}, ensure_ascii=False) + "\\n")
"""


def _install_skills(workspace: Path) -> None:
    source_dir = _get_skills_dir()
    target_dir = workspace / ".claude" / "skills"
    target_dir.mkdir(parents=True)
    for skill_name in _SKILL_NAMES:
        source = source_dir / skill_name
        if not (source / "SKILL.md").is_file():
            raise CLIError(f"Missing preset agent skill: {skill_name}")
        shutil.copytree(source, target_dir / skill_name)


def _get_skills_dir() -> Path:
    source_path = Path(__file__).resolve()
    candidates = (
        source_path.parent / "resources" / "skills",
        source_path.parents[6] / "skills",
    )
    for candidate in candidates:
        if (candidate / "dstack" / "SKILL.md").is_file():
            return candidate
    raise CLIError("Could not find packaged dstack skills")
