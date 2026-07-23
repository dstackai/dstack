import asyncio
import json
import os
import shutil
import signal
import subprocess
import time
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional, Sequence

import psutil

from dstack._internal.cli.models.preset_agent import AGENT_FINAL_REPORT_JSON_SCHEMA
from dstack._internal.cli.services.presets.redaction import redact, redact_structure
from dstack._internal.cli.services.presets.session import (
    PresetAgentSession,
    _pid_alive,
    _pid_running,
    _process_started_at,
    print_preset_progress,
)
from dstack._internal.cli.services.presets.tail import (
    _FileLineReader,
    _OffsetStore,
    _ProgressTailer,
    _RecordMirror,
)
from dstack._internal.cli.services.presets.workspace import (
    _PROGRESS_ENV,
    PresetAgentWorkspace,
)
from dstack._internal.compat import IS_WINDOWS
from dstack._internal.core.errors import CLIError
from dstack._internal.core.services.configs import ConfigManager
from dstack.api import Client

_CLAUDE_TOOLS = "Bash,Read,Write,Edit,WebFetch,WebSearch,StructuredOutput"
_CLAUDE_EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
_RESUME_DELAYS_SECONDS: tuple[int, ...] = (30, 60, 120)
_RESUME_PROMPT = (
    "The previous agent process was interrupted. Continue where you left off. "
    "Re-check the states of your runs before relying on them: time may have "
    "passed, and tasks or instances may have stopped in the meantime."
)
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
        event = redact_structure(json.loads(text), redacted_values)
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
    stdout_output, _ = await asyncio.gather(
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
    # stderr is tailed with parse_result=False — it feeds the debug trace and
    # advances the persisted offset, but can never contribute report data.
    return stdout_output


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
    stream: "_FileLineReader",
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
