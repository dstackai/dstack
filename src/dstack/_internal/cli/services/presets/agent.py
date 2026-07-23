import asyncio
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Iterator, Optional, Protocol, Sequence

import psutil
import yaml
from rich.text import Text

from dstack._internal.cli.models.configurations import PresetConfiguration
from dstack._internal.cli.models.preset_agent import (
    AGENT_FINAL_REPORT_JSON_SCHEMA,
    ClaudeAgentInfo,
)
from dstack._internal.cli.utils.common import console
from dstack._internal.compat import IS_WINDOWS
from dstack._internal.core.errors import CLIError
from dstack._internal.core.services.configs import ConfigManager
from dstack._internal.utils.common import get_dstack_dir
from dstack.api import Client

_SKILL_NAMES = ("dstack", "dstack-prototyping")
_PROGRESS_FILENAME = "progress.jsonl"
_RUNS_FILENAME = "runs.jsonl"
_TRIALS_FILENAME = "trials.jsonl"
_CONSTRAINTS_FILENAME = "constraints.json"
_FINAL_REPORT_FILENAME = "final_report.json"
_SESSION_FILENAME = "session.json"
_USER_PROMPT_FILENAME = "user_prompt.md"
_PROGRESS_ENV = "DSTACK_PRESET_PROGRESS_LOG"
_REDACTION = "[redacted]"
_CLAUDE_TOOLS = "Bash,Read,Write,Edit,WebFetch,WebSearch,StructuredOutput"
_CLAUDE_EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
_RESUME_DELAYS_SECONDS: tuple[int, ...] = (30, 60, 120)
_RESUME_PROMPT = (
    "The previous agent process was interrupted. Continue where you left off. "
    "Re-check the states of your runs before relying on them: time may have "
    "passed, and tasks or instances may have stopped in the meantime."
)
_MAX_RUN_NAME_LENGTH = 41
_MAX_UNIX_SOCKET_PATH_BYTES = 103
_INHERITED_ENV_NAMES = (
    "PATH",
    "HOME",
    "USER",
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)
_WINDOWS_INHERITED_ENV_NAMES = (
    "APPDATA",
    "COMSPEC",
    "HOMEDRIVE",
    "HOMEPATH",
    "LOCALAPPDATA",
    "PATHEXT",
    "PROGRAMDATA",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "USERPROFILE",
    "USERNAME",
    "WINDIR",
)
_SENSITIVE_INHERITED_ENV_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)


class SessionBusyError(CLIError):
    """Another live process owns the session — it is following or finalizing it.
    Callers that only want to view can fall back to a read-only follow."""


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


@dataclass
class PresetAgentSession:
    path: Path
    timestamp: str
    debug: bool
    preset_id: str = ""
    # Whether progress lines echo to this process's console (a live attach), on
    # top of always being recorded to agent.log. Background reconcile sets it
    # False so finalizing a detached session stays silent on the read command.
    echo: bool = field(default=True, repr=False)
    _log_enabled: bool = field(default=True, init=False, repr=False)

    @property
    def log_path(self) -> Path:
        return self.path / "agent.log"

    @property
    def trace_path(self) -> Path:
        return self.path / "trace.jsonl"

    @property
    def runs_path(self) -> Path:
        return self.path / _RUNS_FILENAME

    @property
    def trials_path(self) -> Path:
        return self.path / _TRIALS_FILENAME

    def write_prompt(self, prompt: str) -> None:
        _write_private_text(self.path / "prompt.md", prompt + "\n")

    def write_user_prompt(self, user_prompt: str) -> None:
        _write_private_text(self.path / _USER_PROMPT_FILENAME, user_prompt + "\n")

    def read_user_prompt(self) -> Optional[str]:
        try:
            text = (self.path / _USER_PROMPT_FILENAME).read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return text or None

    def write_constraints(self, constraints_text: str) -> None:
        _write_private_text(self.path / _CONSTRAINTS_FILENAME, constraints_text)

    def write_final_report(self, report_text: str) -> None:
        _write_private_text(self.path / _FINAL_REPORT_FILENAME, report_text)

    def write_agent_info(self, auth: "ClaudeAuth") -> None:
        info = ClaudeAgentInfo.parse_obj(
            {
                "executable": auth.executable,
                "version": _get_claude_version(auth),
                "model": {
                    "name": auth.model,
                    "effort": auth.effort or "default",
                },
                "auth": _get_claude_auth_status(auth),
            }
        )
        _write_private_text(
            self.path / "agent.json", json.dumps(json.loads(info.json()), indent=2) + "\n"
        )

    def append_log(self, line: str) -> None:
        if not self._log_enabled:
            return
        try:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
        except OSError as e:
            self._log_enabled = False
            if self.echo:
                console.print(f"[warning]Could not write agent log {self.log_path}: {e}[/]")

    def read_manifest(self) -> dict[str, Any]:
        try:
            manifest = json.loads((self.path / _SESSION_FILENAME).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return manifest if isinstance(manifest, dict) else {}

    def update_manifest(self, **fields: Any) -> None:
        manifest = self.read_manifest()
        manifest.update(fields)
        _write_private_text(self.path / _SESSION_FILENAME, json.dumps(manifest, indent=2) + "\n")

    def record_claude_session_id(self, session_id: str) -> None:
        self.update_manifest(claude_session_id=session_id)

    def finish(self, status: str) -> Path:
        self.update_manifest(status=status)
        return self.path


@dataclass(frozen=True)
class ClaudeAuth:
    api_key: Optional[str]
    executable: str
    effort: Optional[str]
    model: str


@dataclass
class PresetAgentProcessOutput:
    report_data: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    session_id: Optional[str] = None
    made_progress: bool = False


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


def get_presets_dir() -> Path:
    return get_dstack_dir() / "presets"


def create_preset_agent_session(
    configuration: PresetConfiguration,
    *,
    debug: bool = False,
) -> PresetAgentSession:
    if configuration.name is None:
        raise CLIError("The service name is required to save agent output")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%fZ")
    parent = get_presets_dir()
    path: Optional[Path] = None
    try:
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        while True:
            preset_id = secrets.token_hex(4)
            path = parent / preset_id
            try:
                path.mkdir(mode=0o700)
            except FileExistsError:
                continue
            break
        _write_private_text(path / "agent.log", "")
        manifest = {
            "id": preset_id,
            "status": "running",
            "pid": os.getpid(),
            "pid_started_at": _process_started_at(os.getpid()),
            "name": configuration.name,
            "model": getattr(configuration.model, "base", None)
            or getattr(configuration.model, "repo", None),
            "max_trials": configuration.max_trials,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "debug": debug,
        }
        _write_private_text(path / _SESSION_FILENAME, json.dumps(manifest, indent=2) + "\n")
        data = json.loads(configuration.json(exclude_none=True))
        if configuration.env:
            data["env"] = list(configuration.env)
        else:
            data.pop("env", None)
        _write_private_text(
            path / "preset.dstack.yml",
            yaml.safe_dump(data, sort_keys=False),
        )
        if debug:
            _write_private_text(path / "trace.jsonl", "")
    except OSError as e:
        if path is not None:
            shutil.rmtree(path, ignore_errors=True)
        raise CLIError(f"Could not create agent output under {parent}: {e}") from e
    assert path is not None
    return PresetAgentSession(path=path, timestamp=timestamp, debug=debug, preset_id=preset_id)


def _get_claude_version(auth: "ClaudeAuth") -> Optional[str]:
    try:
        result = subprocess.run(
            [auth.executable, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _get_claude_auth_status(auth: "ClaudeAuth") -> dict[str, Any]:
    if auth.api_key:
        return {"authMethod": "api-key"}
    try:
        result = subprocess.run(
            [auth.executable, "auth", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        status = json.loads(result.stdout)
        if isinstance(status, dict):
            return status
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        pass
    return {"authMethod": "unknown"}


def load_resumable_agent_session(preset_id: str) -> PresetAgentSession:
    path = get_presets_dir() / preset_id
    session = PresetAgentSession(path=path, timestamp="", debug=False, preset_id=preset_id)
    manifest = session.read_manifest()
    if not path.is_dir() or not manifest:
        raise CLIError(f"Unknown preset: {preset_id}")
    status = manifest.get("status")
    if status == "success":
        raise CLIError(f"Preset {preset_id} is already created; nothing to resume")
    if status == "failed":
        raise CLIError(f"Preset {preset_id} creation failed and cannot be resumed")
    if status == "running" and session_process_alive(manifest):
        raise CLIError(
            f"Preset {preset_id} is still being created;"
            f" follow it with [code]dstack preset logs -f {preset_id}[/]"
        )
    if not manifest.get("claude_session_id"):
        raise CLIError(f"Preset {preset_id} creation stopped before it started; create a new one")
    session.debug = bool(manifest.get("debug"))
    session.timestamp = str(manifest.get("created_at") or "")
    return session


def _pid_alive(pid: Any, started_at: Any = None) -> bool:
    if not isinstance(pid, int) or pid <= 0 or not psutil.pid_exists(pid):
        return False
    if isinstance(started_at, (int, float)):
        create_time = _process_started_at(pid)
        # A recycled pid has a different start time.
        if create_time is not None and abs(create_time - started_at) > 1.0:
            return False
    return True


def session_process_alive(manifest: dict[str, Any]) -> bool:
    """Whether the session is still worked on: a live agent (possibly
    detached) or a live CLI (possibly between agent retries)."""
    if _pid_alive(manifest.get("agent_pid"), manifest.get("agent_started_at")):
        return True
    pid = manifest.get("pid")
    if not isinstance(pid, int) or pid <= 0 or pid == os.getpid():
        return False
    # Guard the CLI pid with its start time too: after an ungraceful CLI death
    # the OS can recycle the pid, and a bare pid_exists() would read a dead
    # session as still owned (falsely blocking reconcile / follow).
    return _pid_alive(pid, manifest.get("pid_started_at"))


def load_attachable_agent_session(preset_id: str) -> PresetAgentSession:
    path = get_presets_dir() / preset_id
    session = PresetAgentSession(path=path, timestamp="", debug=False, preset_id=preset_id)
    manifest = session.read_manifest()
    if not path.is_dir() or not manifest:
        raise CLIError(f"Unknown preset: {preset_id}")
    status = manifest.get("status")
    if status == "success":
        raise CLIError(f"Preset {preset_id} is already created")
    if status == "failed":
        raise CLIError(f"Preset {preset_id} creation failed")
    if status == "interrupted":
        raise CLIError(
            f"Preset {preset_id} creation was interrupted; resume it with"
            f" [code]dstack preset create -f <config> --resume {preset_id}[/]"
        )
    pid = manifest.get("pid")
    if (
        isinstance(pid, int)
        and pid > 0
        and pid != os.getpid()
        and _pid_alive(pid, manifest.get("pid_started_at"))
    ):
        raise SessionBusyError(
            f"Preset {preset_id} is already being followed by another CLI (pid {pid});"
            f" stop or detach it there with Ctrl+C"
        )
    session.debug = bool(manifest.get("debug"))
    session.timestamp = str(manifest.get("created_at") or "")
    return session


def load_agent_session(preset_id: str) -> PresetAgentSession:
    """Loads a session of any status for read-only inspection (its log)."""
    path = get_presets_dir() / preset_id
    session = PresetAgentSession(path=path, timestamp="", debug=False, preset_id=preset_id)
    if not path.is_dir() or not session.read_manifest():
        raise CLIError(f"Unknown preset: {preset_id}")
    return session


def print_session_log(session: PresetAgentSession) -> None:
    """Prints the session's redacted progress log verbatim (no markup)."""
    try:
        content = session.log_path.read_text(encoding="utf-8")
    except OSError:
        content = ""
    if content.strip():
        console.print(Text(content.rstrip("\n")), soft_wrap=True)
    else:
        console.print(f"No log output yet for session [code]{session.preset_id}[/].")


def mark_session_owner(
    session: PresetAgentSession,
    *,
    project: Optional[str] = None,
    keep_service: Optional[bool] = None,
    claude_model: Optional[str] = None,
) -> None:
    """Records this process as the session's owner (pid + start time) and, when
    given, the finalize context a later detached reconcile needs (project and
    keep-service intent). `None` fields are left untouched."""
    fields: dict[str, Any] = {
        "status": "running",
        "pid": os.getpid(),
        "pid_started_at": _process_started_at(os.getpid()),
    }
    if project is not None:
        fields["project"] = project
    if keep_service is not None:
        fields["keep_service"] = keep_service
    if claude_model is not None:
        fields["claude_model"] = claude_model
    session.update_manifest(**fields)


def session_report_exists(manifest: dict[str, Any]) -> bool:
    """Whether the agent left a final report on disk — the durable completion
    signal a detached session is finalized from."""
    workspace = manifest.get("workspace")
    if not isinstance(workspace, str) or not workspace:
        return False
    return (Path(workspace) / "w" / _FINAL_REPORT_FILENAME).is_file()


def try_claim_session(session: PresetAgentSession) -> Optional[int]:
    """Takes an exclusive, kernel-held lock for the duration of a session's
    finalization, so concurrent readers can't both finalize it. Returns an open
    file descriptor to release via `release_session_claim`, or None if another
    process holds it. The kernel drops the lock if the holder dies, so there are
    no stale locks to reason about."""
    try:
        fd = os.open(session.path / ".reconcile.lock", os.O_CREAT | os.O_RDWR, 0o600)
    except OSError:
        return None
    if _try_lock_fd(fd):
        return fd
    with suppress(OSError):
        os.close(fd)
    return None


def release_session_claim(fd: Optional[int]) -> None:
    if fd is not None:
        # Closing the descriptor releases the kernel lock.
        with suppress(OSError):
            os.close(fd)


def _try_lock_fd(fd: int) -> bool:
    """Non-blocking exclusive lock on an open fd; True if acquired, False if
    another process holds it."""
    if IS_WINDOWS:
        import msvcrt

        try:
            # A 1-byte range lock at offset 0 (allowed past EOF on Windows).
            msvcrt.locking(  # pyright: ignore[reportAttributeAccessIssue]
                fd,
                msvcrt.LK_NBLCK,  # pyright: ignore[reportAttributeAccessIssue]
                1,
            )
            return True
        except OSError:
            return False
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def claimed_session_name(manifest: dict[str, Any]) -> Optional[str]:
    """The name this session holds."""
    value = manifest.get("name")
    return value if isinstance(value, str) and value else None


def iter_agent_sessions() -> Iterator[PresetAgentSession]:
    """Yields a handle for every session directory under the presets dir."""
    root = get_presets_dir()
    if not root.is_dir():
        return
    for path in sorted(root.iterdir()):
        if path.is_dir() and not path.name.startswith((".", "models--")):
            yield PresetAgentSession(path=path, timestamp="", debug=False, preset_id=path.name)


def find_session_name_claims(name: str) -> list[PresetAgentSession]:
    """Sessions of any status holding `name`, including failed ones."""
    return [
        session
        for session in iter_agent_sessions()
        if claimed_session_name(session.read_manifest()) == name
    ]


def list_agent_sessions() -> list[dict[str, Any]]:
    entries = []
    for session in iter_agent_sessions():
        path = session.path
        manifest = session.read_manifest()
        status = manifest.get("status")
        if status not in ("running", "interrupted", "success"):
            continue
        if status == "running" and not session_process_alive(manifest):
            status = "interrupted"
        entry = dict(manifest)
        entry["id"] = path.name
        entry["name"] = claimed_session_name(manifest)
        entry["status"] = status
        entry["trials"] = _summarize_session_trials(path / _TRIALS_FILENAME)
        entries.append(entry)
    return entries


def _summarize_session_trials(path: Path) -> Optional[dict[str, Any]]:
    """Best-so-far summary from a session's mirrored trial records."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    count = 0
    best: Optional[dict[str, Any]] = None
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        # One record per trial (the agent contract); trials may share a task,
        # so task names must not be deduplicated.
        count += 1
        benchmark = record.get("benchmark")
        if not isinstance(benchmark, dict):
            continue
        metrics = benchmark.get("metrics") or {}
        workload = benchmark.get("workload") or {}
        duration = metrics.get("duration_seconds")
        tokens = metrics.get("total_output_tokens")
        if not isinstance(duration, (int, float)) or duration <= 0:
            continue
        if not isinstance(tokens, (int, float)):
            continue
        tok_s = tokens / duration
        if best is None or tok_s > best["tok_s"]:
            resources = record.get("resources") or {}
            gpu = resources.get("gpu") if isinstance(resources, dict) else None
            gpu_text = None
            if isinstance(gpu, dict) and gpu.get("name"):
                gpu_text = str(gpu["name"])
                if gpu.get("memory"):
                    gpu_text += f":{gpu['memory']}"
                if gpu.get("count"):
                    gpu_text += f":{gpu['count']}"
            best = {
                "tok_s": tok_s,
                "concurrency": workload.get("concurrency"),
                "gpu": gpu_text,
            }
    return {"count": count, "best": best}


def get_claude_auth() -> ClaudeAuth:
    api_key = os.getenv("DSTACK_AGENT_ANTHROPIC_API_KEY") or None
    configured_path = os.getenv("DSTACK_AGENT_CLAUDE_PATH") or "claude"
    executable = shutil.which(configured_path)
    if executable is None:
        raise CLIError(f"Claude executable not found: {configured_path}")
    effort = os.getenv("DSTACK_AGENT_CLAUDE_EFFORT") or None
    if effort is not None and effort not in _CLAUDE_EFFORT_LEVELS:
        raise CLIError(
            f"DSTACK_AGENT_CLAUDE_EFFORT must be one of: {', '.join(_CLAUDE_EFFORT_LEVELS)}"
        )
    return ClaudeAuth(
        api_key=api_key,
        executable=executable,
        effort=effort,
        model=os.getenv("DSTACK_AGENT_ANTHROPIC_MODEL", "claude-opus-4-8"),
    )


def build_preset_agent_env(
    *,
    api: Client,
    preset_env: dict[str, str],
    auth: ClaudeAuth,
    workspace: PresetAgentWorkspace,
    token: str,
) -> dict[str, str]:
    config_manager = ConfigManager(workspace.dstack_home / ".dstack")
    config_manager.configure_project(
        name=api.project,
        url=api.client.base_url,
        token=token,
        default=True,
    )
    config_manager.save()
    env = {name: value for name in _INHERITED_ENV_NAMES if (value := os.getenv(name))}
    env.update(preset_env)
    if IS_WINDOWS:
        env.update(
            {name: value for name in _WINDOWS_INHERITED_ENV_NAMES if (value := os.getenv(name))}
        )
    env["PATH"] = os.pathsep.join([str(workspace.bin_path), env.get("PATH", "")])
    env["DSTACK_SERVER_URL"] = api.client.base_url
    env["DSTACK_PROJECT"] = api.project
    env["DSTACK_TOKEN"] = token
    env[_PROGRESS_ENV] = str(workspace.progress_path)
    for name in ["TMPDIR", "TEMP", "TMP"]:
        env[name] = str(workspace.temp_path)
    if auth.api_key is not None:
        env["ANTHROPIC_API_KEY"] = auth.api_key
        env["HOME"] = str(workspace.dstack_home)
        if IS_WINDOWS:
            env["USERPROFILE"] = str(workspace.dstack_home)
    else:
        env["HOME"] = str(Path.home())
        if IS_WINDOWS:
            env["USERPROFILE"] = str(Path.home())
    return env


async def run_preset_agent(
    *,
    prompt: str,
    env: dict[str, str],
    workspace: PresetAgentWorkspace,
    auth: ClaudeAuth,
    redacted_values: Sequence[str],
    agent_session: PresetAgentSession,
    initial_resume_session_id: Optional[str] = None,
) -> PresetAgentProcessOutput:
    async with _session_tailers(
        workspace=workspace, agent_session=agent_session, redacted_values=redacted_values
    ):
        resume_session_id: Optional[str] = initial_resume_session_id
        attempt_prompt = prompt if resume_session_id is None else _RESUME_PROMPT
        retry_delays = list(_RESUME_DELAYS_SECONDS)
        while True:
            command = _prepare_subprocess_command(
                _build_claude_command(auth=auth, resume_session_id=resume_session_id)
            )
            output, returncode = await _run_claude_process(
                command=command,
                prompt=attempt_prompt,
                env=env,
                workspace=workspace,
                redacted_values=redacted_values,
                agent_session=agent_session,
            )
            if output.report_data is None and returncode != 0:
                output.error = output.error or f"Claude exited with return code {returncode}"
            # Retry any process death without a submitted report; a terminal
            # failure report from the agent returns immediately.
            if output.report_data is not None or output.error is None:
                return output
            # A failed attempt that produced agent work is a new outage, not a
            # continuation of the previous one: restore the full retry budget.
            # Attempts that fail without any work drain it, so the loop always
            # terminates when the network stays down.
            if output.made_progress:
                retry_delays = list(_RESUME_DELAYS_SECONDS)
            if not retry_delays:
                return output
            delay = retry_delays.pop(0)
            session_id = output.session_id or resume_session_id
            if session_id is not None:
                resume_session_id = session_id
                attempt_prompt = _RESUME_PROMPT
                action = "resuming"
            else:
                action = "retrying"
            print_preset_progress(
                f"Agent process exited without a report; {action} in {delay}s.",
                agent_session=agent_session,
            )
            await asyncio.sleep(delay)


async def _run_claude_process(
    *,
    command: list[str],
    prompt: str,
    env: dict[str, str],
    workspace: PresetAgentWorkspace,
    redacted_values: Sequence[str],
    agent_session: PresetAgentSession,
) -> tuple[PresetAgentProcessOutput, int]:
    proc: Optional[asyncio.subprocess.Process] = None
    try:
        # The agent's streams go to workspace files rather than pipes, so the
        # agent survives CLI death (detach) and a later attach can continue
        # parsing from the persisted offsets.
        with (
            workspace.agent_stdout_path.open("ab") as stdout_file,
            workspace.agent_stderr_path.open("ab") as stderr_file,
        ):
            proc = await asyncio.create_subprocess_exec(
                *command,
                cwd=workspace.path,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=not IS_WINDOWS,
                # Inherit only the redirected std handles, not the CLI's other fds.
                # Without this the untrusted agent inherits our open descriptors, and
                # on Windows the broad inheritance flakes CreateProcess (WinError 87).
                close_fds=True,
            )
        agent_session.update_manifest(
            agent_pid=proc.pid, agent_started_at=_process_started_at(proc.pid)
        )
        assert proc.stdin is not None
        proc.stdin.write(prompt.encode())
        with suppress(BrokenPipeError, ConnectionResetError):
            await proc.stdin.drain()
        proc.stdin.close()

        def agent_alive() -> bool:
            return proc.returncode is None

        collect_task = asyncio.create_task(
            _collect_agent_output(
                workspace=workspace,
                agent_session=agent_session,
                redacted_values=redacted_values,
                is_alive=agent_alive,
            )
        )
        returncode = await proc.wait()
        output = await collect_task
    except (KeyboardInterrupt, asyncio.CancelledError):
        # The stop-or-detach decision belongs to the interrupt handler; the
        # agent must stay alive here in case the user detaches.
        raise
    except BaseException:
        if proc is not None and proc.returncode is None:
            await _terminate_process(proc)
        raise

    return output, returncode


def print_preset_progress(message: str, *, agent_session: PresetAgentSession) -> None:
    timestamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    message = message.rstrip("\r\n")
    agent_session.append_log(f"[{timestamp}] {message}")
    if not agent_session.echo:
        return
    console.print(
        Text(f"[{timestamp}]", style="log.time"),
        Text(message, style="log.message"),
        soft_wrap=True,
    )


def get_redacted_values(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value}, key=len, reverse=True))


def contains_redacted_value(value: Any, redacted_values: Sequence[str]) -> bool:
    if isinstance(value, str):
        return any(
            value == redacted or (len(redacted) >= 8 and redacted in value)
            for redacted in redacted_values
        )
    if isinstance(value, dict):
        return any(contains_redacted_value(item, redacted_values) for item in value.values())
    if isinstance(value, list):
        return any(contains_redacted_value(item, redacted_values) for item in value)
    return False


def get_sensitive_inherited_env_values() -> list[str]:
    return [value for name in _SENSITIVE_INHERITED_ENV_NAMES if (value := os.getenv(name))]


def redact(value: str, redacted_values: Sequence[str]) -> str:
    for redacted_value in redacted_values:
        if value == redacted_value:
            return _REDACTION
        # Replacing short values such as "1" or "false" corrupts unrelated diagnostics.
        if len(redacted_value) >= 8:
            value = value.replace(redacted_value, _REDACTION)
    return value


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


def _build_claude_command(
    *, auth: ClaudeAuth, resume_session_id: Optional[str] = None
) -> list[str]:
    command = [
        auth.executable,
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--tools",
        _CLAUDE_TOOLS,
        "--allowedTools",
        _CLAUDE_TOOLS,
        "--disallowedTools",
        "Task,NotebookEdit",
        "--permission-mode",
        "bypassPermissions",
        "--model",
        auth.model,
        "--json-schema",
        json.dumps(AGENT_FINAL_REPORT_JSON_SCHEMA),
    ]
    if auth.api_key is None:
        command[2:2] = ["--setting-sources", "project,local"]
    else:
        command[2:2] = ["--bare"]
    if auth.effort is not None:
        command[2:2] = ["--effort", auth.effort]
    if resume_session_id is not None:
        command += ["--resume", resume_session_id]
    return command


def _prepare_subprocess_command(command: list[str]) -> list[str]:
    if not IS_WINDOWS or Path(command[0]).suffix.lower() not in {".bat", ".cmd"}:
        return command
    comspec = os.getenv("COMSPEC") or shutil.which("cmd.exe")
    if comspec is None:
        raise CLIError("Cannot run the Claude batch launcher because cmd.exe was not found")
    return [comspec, "/d", "/s", "/c", subprocess.list2cmdline(command)]


def _write_private_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    if not IS_WINDOWS:
        path.chmod(0o600)


def _write_debug_trace(
    session: PresetAgentSession,
    *,
    stream_name: str,
    text: str,
    redacted_values: Sequence[str],
) -> None:
    timestamp = (
        datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )
    try:
        event = _redact_trace_value(json.loads(text), redacted_values)
        record = {"timestamp": timestamp, "stream": stream_name, "event": event}
    except json.JSONDecodeError:
        record = {
            "timestamp": timestamp,
            "stream": stream_name,
            "text": redact(text.rstrip("\r\n"), redacted_values),
        }
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with session.trace_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()


def _redact_trace_value(value: Any, redacted_values: Sequence[str]) -> Any:
    if isinstance(value, str):
        return redact(value, redacted_values)
    if isinstance(value, list):
        return [_redact_trace_value(item, redacted_values) for item in value]
    if isinstance(value, dict):
        return {
            redact(key, redacted_values): _redact_trace_value(item, redacted_values)
            for key, item in value.items()
        }
    return value


@asynccontextmanager
async def _session_tailers(
    *,
    workspace: PresetAgentWorkspace,
    agent_session: PresetAgentSession,
    redacted_values: Sequence[str],
) -> AsyncIterator[None]:
    """Mirrors the session's progress and record files while the body runs."""
    offset_store = _OffsetStore(agent_session.path / ".offsets.json")
    progress_tailer = _ProgressTailer(
        path=workspace.progress_path,
        redacted_values=redacted_values,
        agent_session=agent_session,
        offset_store=offset_store,
    )
    record_mirrors = [
        _RecordMirror(
            source=workspace.runs_path,
            target=agent_session.runs_path,
            redacted_values=redacted_values,
            offset_store=offset_store,
            offset_key="runs",
            echo=agent_session.echo,
        ),
        _RecordMirror(
            source=workspace.trials_path,
            target=agent_session.trials_path,
            redacted_values=redacted_values,
            offset_store=offset_store,
            offset_key="trials",
            echo=agent_session.echo,
        ),
    ]
    tailer_tasks = [
        asyncio.create_task(tailer.run()) for tailer in [progress_tailer, *record_mirrors]
    ]
    try:
        yield
    finally:
        for task in tailer_tasks:
            task.cancel()
        for task in tailer_tasks:
            with suppress(asyncio.CancelledError):
                await task
        progress_tailer.flush()
        for mirror in record_mirrors:
            mirror.flush()


async def _collect_agent_output(
    *,
    workspace: PresetAgentWorkspace,
    agent_session: PresetAgentSession,
    redacted_values: Sequence[str],
    is_alive: Callable[[], bool],
) -> PresetAgentProcessOutput:
    """Parses the agent's stream files until it exits; safe alongside a live
    process or over the remains of a finished one."""
    offset_store = _OffsetStore(agent_session.path / ".offsets.json")
    stdout_output, stderr_output = await asyncio.gather(
        _read_process_stream(
            stream=_FileLineReader(
                workspace.agent_stdout_path,
                offset_store=offset_store,
                offset_key="agent_stdout",
                is_alive=is_alive,
            ),
            stream_name="stdout",
            parse_result=True,
            redacted_values=redacted_values,
            agent_session=agent_session,
        ),
        _read_process_stream(
            stream=_FileLineReader(
                workspace.agent_stderr_path,
                offset_store=offset_store,
                offset_key="agent_stderr",
                is_alive=is_alive,
            ),
            stream_name="stderr",
            parse_result=False,
            redacted_values=redacted_values,
            agent_session=agent_session,
        ),
    )
    output = stdout_output
    if output.report_data is None:
        output.report_data = stderr_output.report_data
    if output.error is None:
        output.error = stderr_output.error
    return output


async def attach_preset_agent(
    *,
    workspace: PresetAgentWorkspace,
    redacted_values: Sequence[str],
    agent_session: PresetAgentSession,
) -> PresetAgentProcessOutput:
    """Follows a detached session's agent to completion, like
    `run_preset_agent` without owning the process."""
    async with _session_tailers(
        workspace=workspace, agent_session=agent_session, redacted_values=redacted_values
    ):
        manifest = agent_session.read_manifest()

        def agent_alive() -> bool:
            return _pid_alive(manifest.get("agent_pid"), manifest.get("agent_started_at"))

        return await _collect_agent_output(
            workspace=workspace,
            agent_session=agent_session,
            redacted_values=redacted_values,
            is_alive=agent_alive,
        )


async def _read_process_stream(
    *,
    stream: "_LineStream",
    stream_name: str,
    parse_result: bool,
    redacted_values: Sequence[str],
    agent_session: PresetAgentSession,
) -> PresetAgentProcessOutput:
    output = PresetAgentProcessOutput()
    while True:
        line = await stream.readline()
        if not line:
            return output
        text = line.decode(errors="replace")
        if agent_session.debug:
            _write_debug_trace(
                agent_session,
                stream_name=stream_name,
                text=text,
                redacted_values=redacted_values,
            )
        if not parse_result:
            continue
        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(message, dict):
            continue
        if output.session_id is None:
            session_id = message.get("session_id")
            if isinstance(session_id, str) and session_id:
                output.session_id = session_id
                agent_session.record_claude_session_id(session_id)
        if message.get("type") == "assistant":
            output.made_progress = True
        if message.get("type") != "result":
            continue
        if message.get("is_error"):
            error = message.get("result") or "Claude failed"
            output.error = redact(str(error), redacted_values)
        structured_output = message.get("structured_output")
        if isinstance(structured_output, dict):
            output.report_data = structured_output
            continue
        result = message.get("result")
        if isinstance(result, str):
            try:
                parsed = json.loads(result)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                output.report_data = parsed


async def _terminate_process(proc: asyncio.subprocess.Process) -> None:
    if IS_WINDOWS:
        await asyncio.to_thread(_terminate_windows_process_tree, proc.pid)
        await proc.wait()
        return
    # The Windows branch returns above; Pyright still checks these POSIX-only APIs on Windows.
    if hasattr(os, "killpg"):
        with suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)  # pyright: ignore[reportAttributeAccessIssue]
    else:
        proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=3)
    except asyncio.TimeoutError:
        if hasattr(os, "killpg"):
            with suppress(ProcessLookupError):
                os.killpg(  # pyright: ignore[reportAttributeAccessIssue]
                    proc.pid,
                    signal.SIGKILL,  # pyright: ignore[reportAttributeAccessIssue]
                )
        else:
            proc.kill()
        await proc.wait()


def terminate_agent_process(manifest: dict[str, Any]) -> None:
    """Terminates the session's agent process tree, if alive."""
    agent_pid = manifest.get("agent_pid")
    if not isinstance(agent_pid, int) or not _pid_alive(
        agent_pid, manifest.get("agent_started_at")
    ):
        return
    if IS_WINDOWS:
        _terminate_windows_process_tree(agent_pid)
        return
    with suppress(OSError):
        os.killpg(agent_pid, signal.SIGTERM)  # pyright: ignore[reportAttributeAccessIssue]
    for _ in range(30):
        if not _pid_running(agent_pid):
            return
        time.sleep(0.1)
    with suppress(OSError):
        os.killpg(agent_pid, signal.SIGKILL)  # pyright: ignore[reportAttributeAccessIssue]


def _pid_running(pid: int) -> bool:
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


def _process_started_at(pid: int) -> Optional[float]:
    try:
        return psutil.Process(pid).create_time()
    except psutil.Error:
        return None


def _terminate_windows_process_tree(pid: int) -> None:
    try:
        root = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    processes = [*root.children(recursive=True), root]
    for process in processes:
        with suppress(psutil.NoSuchProcess):
            process.terminate()
    _, alive = psutil.wait_procs(processes, timeout=3)
    for process in alive:
        with suppress(psutil.NoSuchProcess):
            process.kill()
    psutil.wait_procs(alive, timeout=3)


class _LineStream(Protocol):
    async def readline(self) -> bytes: ...


class _FileLineReader:
    """`readline()` over a growing file, so stream parsing survives CLI
    restarts: offsets persist, and a later attach continues exactly where the
    previous reader stopped."""

    _POLL_SECONDS = 0.2
    _MAX_CHUNK = 1024 * 1024

    def __init__(
        self,
        path: Path,
        *,
        offset_store: "_OffsetStore",
        offset_key: str,
        is_alive: Callable[[], bool],
    ) -> None:
        self._path = path
        self._offset_store = offset_store
        self._offset_key = offset_key
        self._is_alive = is_alive
        self._offset = offset_store.get(offset_key)
        self._buffer = b""
        self._drained = False

    def _read_chunk(self) -> bytes:
        try:
            with self._path.open("rb") as f:
                f.seek(self._offset)
                return f.read(self._MAX_CHUNK)
        except OSError:
            return b""

    async def readline(self) -> bytes:
        while True:
            if b"\n" in self._buffer:
                line, self._buffer = self._buffer.split(b"\n", 1)
                return line + b"\n"
            chunk = self._read_chunk()
            if chunk:
                self._buffer += chunk
                self._offset += len(chunk)
                self._offset_store.set(self._offset_key, self._offset)
                continue
            if not self._is_alive():
                if self._drained:
                    # A final partial line without a newline, then EOF.
                    line, self._buffer = self._buffer, b""
                    return line
                # One more read after death to catch the last flush.
                self._drained = True
                continue
            await asyncio.sleep(self._POLL_SECONDS)


class _OffsetStore:
    """Persists tailer/mirror byte offsets so resumed sessions do not repeat output."""

    def __init__(self, path: Path) -> None:
        self._path = path
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        self._data: dict[str, Any] = data if isinstance(data, dict) else {}

    def get(self, key: str) -> int:
        value = self._data.get(key, 0)
        return value if isinstance(value, int) and value >= 0 else 0

    def set(self, key: str, value: int) -> None:
        self._data[key] = value
        # Re-read and update only this key: several stores (stream readers and
        # record mirrors) share one file with disjoint keys, and writing the
        # whole in-memory view would clobber the others' offsets.
        try:
            on_disk = json.loads(self._path.read_text(encoding="utf-8"))
            data = on_disk if isinstance(on_disk, dict) else {}
        except (OSError, json.JSONDecodeError):
            data = {}
        data[key] = value
        with suppress(OSError):
            _write_private_text(self._path, json.dumps(data) + "\n")


class _ProgressTailer:
    def __init__(
        self,
        *,
        path: Path,
        redacted_values: Sequence[str],
        agent_session: PresetAgentSession,
        offset_store: Optional[_OffsetStore] = None,
        offset_key: str = "progress",
    ) -> None:
        self._path = path
        self._redacted_values = redacted_values
        self._agent_session = agent_session
        self._offset_store = offset_store
        self._offset_key = offset_key
        self._offset = offset_store.get(offset_key) if offset_store else 0

    async def run(self) -> None:
        while True:
            self.flush()
            await asyncio.sleep(1)

    def flush(self) -> None:
        if not self._path.exists():
            return
        with self._path.open("r", encoding="utf-8", errors="replace") as f:
            f.seek(self._offset)
            lines = f.readlines()
            self._offset = f.tell()
        if lines and self._offset_store is not None:
            self._offset_store.set(self._offset_key, self._offset)
        for line in lines:
            message = _parse_progress(line)
            if message is not None:
                print_preset_progress(
                    redact(message, self._redacted_values),
                    agent_session=self._agent_session,
                )


class _RecordMirror:
    """Mirrors a workspace record file into the persistent session directory, redacted."""

    def __init__(
        self,
        *,
        source: Path,
        target: Path,
        redacted_values: Sequence[str],
        offset_store: Optional[_OffsetStore] = None,
        offset_key: str = "",
        echo: bool = True,
    ) -> None:
        self._source = source
        self._target = target
        self._redacted_values = redacted_values
        self._offset_store = offset_store
        self._offset_key = offset_key
        self._offset = offset_store.get(offset_key) if offset_store and offset_key else 0
        self._enabled = True
        self._echo = echo

    async def run(self) -> None:
        while True:
            self.flush()
            await asyncio.sleep(1)

    def flush(self) -> None:
        if not self._enabled or not self._source.exists():
            return
        with self._source.open("rb") as f:
            f.seek(self._offset)
            data = f.read()
        # Mirror complete lines only; a partial line is kept for the next flush.
        end = data.rfind(b"\n")
        if end < 0:
            return
        chunk = data[: end + 1].decode("utf-8", errors="replace")
        self._offset += end + 1
        if self._offset_store is not None and self._offset_key:
            self._offset_store.set(self._offset_key, self._offset)
        try:
            if not self._target.exists():
                _write_private_text(self._target, "")
            # newline="" writes the binary-read chunk verbatim. Without it, text mode
            # re-translates "\n" to "\r\n" on Windows, doubling the "\r\n" a text-written
            # source already carries ("\r\r\n"), which reads back as a blank extra line.
            with self._target.open("a", encoding="utf-8", newline="") as f:
                f.write(redact(chunk, self._redacted_values))
                f.flush()
        except OSError as e:
            self._enabled = False
            if self._echo:
                console.print(f"[warning]Could not mirror {self._target.name}: {e}[/]")


def _parse_progress(line: str) -> Optional[str]:
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return line.strip() or None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict) and isinstance(value.get("message"), str):
        return value["message"].strip() or None
    return None
