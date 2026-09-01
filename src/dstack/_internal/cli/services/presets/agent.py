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
from typing import Any, AsyncIterator, Callable, Iterable, Literal, Optional, Sequence, get_args

import psutil
from pydantic import ValidationError

from dstack._internal.cli.models.preset_agent import (
    AnyClaudeStreamEvent,
    ClaudeResultEvent,
    PresetAgentFailure,
    PresetAgentSuccess,
    PresetSessionProcess,
)
from dstack._internal.cli.services.presets.redaction import redact, redact_structure
from dstack._internal.cli.services.presets.session import (
    PresetSession,
    pid_running,
    print_preset_progress,
    process_alive,
    process_started_at,
)
from dstack._internal.cli.services.presets.tail import (
    DirectoryMirror,
    FileLineReader,
    OffsetStore,
    ProgressTailer,
    RecordMirror,
    open_session_offsets,
)
from dstack._internal.cli.services.presets.workspace import (
    PROGRESS_ENV,
    PresetAgentWorkspace,
)
from dstack._internal.compat import IS_WINDOWS
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.common import validate_json_extra_ignore
from dstack._internal.core.services.configs import ConfigManager
from dstack.api import Client

_CLAUDE_TOOLS = "Bash,Read,Write,Edit,WebFetch,WebSearch,StructuredOutput"
ClaudeEffort = Literal["low", "medium", "high", "xhigh", "max"]
_RESUME_DELAYS_SECONDS: tuple[int, ...] = (30, 60, 120)
_TERMINATE_GRACE_SECONDS = 3
_AGENT_ERROR_MAX_LENGTH = 200
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
    # None uses the claude CLI's own default.
    effort: Optional[ClaudeEffort]
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


def _get_claude_auth_status(auth: "ClaudeAuth") -> str:
    if auth.api_key:
        return "api-key"
    try:
        result = subprocess.run(
            [auth.executable, "auth", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def get_claude_auth() -> ClaudeAuth:
    api_key = os.getenv("DSTACK_AGENT_ANTHROPIC_API_KEY") or None
    configured_path = os.getenv("DSTACK_AGENT_CLAUDE_PATH") or "claude"
    executable = shutil.which(configured_path)
    if executable is None:
        raise CLIError(f"Claude executable not found: {configured_path}")
    effort = os.getenv("DSTACK_AGENT_CLAUDE_EFFORT") or None
    if effort is not None and effort not in get_args(ClaudeEffort):
        raise CLIError(
            f"DSTACK_AGENT_CLAUDE_EFFORT must be one of: {', '.join(get_args(ClaudeEffort))}"
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
    env[PROGRESS_ENV] = str(workspace.progress_path)
    for name in ["TMPDIR", "TEMP", "TMP"]:
        env[name] = str(workspace.temp_path)
    # Sandbox the agent's Claude config under the workspace home when we pass our
    # own API key; under subscription auth keep the real HOME so it reuses the
    # user's existing `claude` login.
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
    session: PresetSession,
    initial_resume_session_id: Optional[str] = None,
) -> PresetAgentProcessOutput:
    offset_store = open_session_offsets(session)
    async with _session_tailers(
        workspace=workspace,
        session=session,
        redacted_values=redacted_values,
        offset_store=offset_store,
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
                session=session,
                offset_store=offset_store,
            )
            if output.report_data is None and returncode != 0:
                output.error = output.error or f"Claude exited with return code {returncode}"
            error = output.error
            # Retry any process death without a submitted report; a terminal
            # failure report from the agent returns immediately.
            if output.report_data is not None or error is None:
                return output
            # Only reset the retry budget when the last attempt made progress; a
            # run that keeps stalling exhausts its retries instead of retrying a
            # stuck agent forever.
            if output.made_progress:
                retry_delays = list(_RESUME_DELAYS_SECONDS)
            # Another process marked this session interrupted; don't restart it.
            state = session.read_state()
            if state is not None and state.status == "interrupted":
                return output
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
                f"Agent process exited without a report: {_format_agent_error(error)};"
                f" {action} in {delay}s.",
                session=session,
            )
            await asyncio.sleep(delay)


async def _run_claude_process(
    *,
    command: list[str],
    prompt: str,
    env: dict[str, str],
    workspace: PresetAgentWorkspace,
    redacted_values: Sequence[str],
    session: PresetSession,
    offset_store: OffsetStore,
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
                # So the untrusted agent inherits only the redirected std handles,
                # not our other descriptors; broad inheritance also flakes
                # CreateProcess on Windows (WinError 87).
                close_fds=True,
            )
        session.record_agent(
            PresetSessionProcess(pid=proc.pid, started_at=process_started_at(proc.pid))
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
                session=session,
                redacted_values=redacted_values,
                is_alive=agent_alive,
                offset_store=offset_store,
            )
        )
        descendants = _process_descendants(proc.pid)
        descendant_watcher = asyncio.create_task(_watch_process_descendants(proc.pid, descendants))
        try:
            returncode = await proc.wait()
            output = await collect_task
        finally:
            descendant_watcher.cancel()
            with suppress(asyncio.CancelledError):
                await descendant_watcher
            _terminate_processes(descendants.values())
            # Never leave the collector orphaned when an await above raises
            # (cancellation, interrupt, or a wait failure).
            if not collect_task.done():
                collect_task.cancel()
                with suppress(asyncio.CancelledError):
                    await collect_task
    except (KeyboardInterrupt, asyncio.CancelledError):
        # The stop-or-detach decision belongs to the interrupt handler; the
        # agent must stay alive here in case the user detaches.
        raise
    except BaseException:
        if proc is not None and proc.returncode is None:
            await _terminate_process(proc)
        raise

    return output, returncode


def _build_claude_command(*, auth: ClaudeAuth, resume_session_id: Optional[str]) -> list[str]:
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
        json.dumps(_get_report_json_schema()),
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
    """On Windows a `.bat`/`.cmd` Claude launcher can't be exec'd directly; wrap
    it in `cmd.exe /c`. Every other case is returned unchanged."""
    if not IS_WINDOWS or Path(command[0]).suffix.lower() not in {".bat", ".cmd"}:
        return command
    comspec = os.getenv("COMSPEC") or shutil.which("cmd.exe")
    if comspec is None:
        raise CLIError("Cannot run the Claude batch launcher because cmd.exe was not found")
    return [comspec, "/d", "/s", "/c", subprocess.list2cmdline(command)]


def _format_agent_error(error: str) -> str:
    """Squashes the agent's error onto one progress line. The error is redacted
    where it is captured; collapsing whitespace and truncating cannot undo that."""
    text = " ".join(error.split())
    if len(text) > _AGENT_ERROR_MAX_LENGTH:
        text = text[:_AGENT_ERROR_MAX_LENGTH].rstrip() + "..."
    return text


def _write_trace(
    session: PresetSession,
    *,
    stream_name: Literal["stdout", "stderr"],
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
    session: PresetSession,
    redacted_values: Sequence[str],
    offset_store: OffsetStore,
) -> AsyncIterator[None]:
    progress_tailer = ProgressTailer(
        path=workspace.progress_path,
        redacted_values=redacted_values,
        session=session,
        offset_store=offset_store,
    )
    record_mirrors = [
        RecordMirror(
            source=workspace.runs_path,
            target=session.runs_path,
            redacted_values=redacted_values,
            offset_store=offset_store,
            offset_key="runs",
            echo=session.echo,
        ),
        DirectoryMirror(
            source=workspace.trials_dir,
            target=session.trials_dir,
            redacted_values=redacted_values,
            echo=session.echo,
        ),
        DirectoryMirror(
            source=workspace.service_dir,
            target=session.service_dir,
            redacted_values=redacted_values,
            echo=session.echo,
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
    session: PresetSession,
    redacted_values: Sequence[str],
    is_alive: Callable[[], bool],
    offset_store: OffsetStore,
) -> PresetAgentProcessOutput:
    """Safe to run alongside a live agent or over the stream files a finished one left behind."""
    stdout_output, _ = await asyncio.gather(
        _read_process_stream(
            stream=FileLineReader(
                workspace.agent_stdout_path,
                offset_store=offset_store,
                offset_key="agent_stdout",
                is_alive=is_alive,
            ),
            stream_name="stdout",
            redacted_values=redacted_values,
            session=session,
        ),
        _read_process_stream(
            stream=FileLineReader(
                workspace.agent_stderr_path,
                offset_store=offset_store,
                offset_key="agent_stderr",
                is_alive=is_alive,
            ),
            stream_name="stderr",
            redacted_values=redacted_values,
            session=session,
        ),
    )
    return stdout_output


async def attach_preset_agent(
    *,
    workspace: PresetAgentWorkspace,
    redacted_values: Sequence[str],
    session: PresetSession,
) -> PresetAgentProcessOutput:
    """Like `run_preset_agent`, but tails a detached agent it does not own."""
    offset_store = open_session_offsets(session)
    async with _session_tailers(
        workspace=workspace,
        session=session,
        redacted_values=redacted_values,
        offset_store=offset_store,
    ):
        state = session.read_state()

        def agent_alive() -> bool:
            return state is not None and state.run is not None and process_alive(state.run.agent)

        return await _collect_agent_output(
            workspace=workspace,
            session=session,
            redacted_values=redacted_values,
            is_alive=agent_alive,
            offset_store=offset_store,
        )


async def _read_process_stream(
    *,
    stream: "FileLineReader",
    stream_name: Literal["stdout", "stderr"],
    redacted_values: Sequence[str],
    session: PresetSession,
) -> PresetAgentProcessOutput:
    # stderr feeds the trace and advances the persisted offset, but only
    # stdout can carry the report.
    parse_result = stream_name == "stdout"
    output = PresetAgentProcessOutput()
    while True:
        line = await stream.readline()
        if not line:
            return output
        text = line.decode(errors="replace")
        _write_trace(
            session,
            stream_name=stream_name,
            text=text,
            redacted_values=redacted_values,
        )
        if not parse_result:
            continue
        try:
            event = validate_json_extra_ignore(AnyClaudeStreamEvent, text)
        except ValidationError:
            continue
        if output.session_id is None and event.session_id:
            output.session_id = event.session_id
            session.record_claude_session_id(event.session_id)
        if event.type == "assistant":
            output.made_progress = True
        if not isinstance(event, ClaudeResultEvent):
            continue
        if event.is_error:
            output.error = redact(str(event.result or "Claude failed"), redacted_values)
        if event.structured_output is not None:
            output.report_data = event.structured_output
            continue
        # An agent may print the report as its final text instead of submitting
        # it through `StructuredOutput`.
        if isinstance(event.result, str):
            try:
                parsed = json.loads(event.result)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                output.report_data = parsed


async def _terminate_process(proc: asyncio.subprocess.Process) -> None:
    """Twin of `terminate_agent_process` for a process this CLI owns, driven through its handle."""
    if IS_WINDOWS:
        await asyncio.to_thread(_terminate_windows_process_tree, proc.pid)
        await proc.wait()
        return
    _terminate_processes(_process_descendants(proc.pid).values())
    # The Windows branch returns above; Pyright still checks these POSIX-only APIs on Windows.
    if hasattr(os, "killpg"):
        with suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)  # pyright: ignore[reportAttributeAccessIssue]
    else:
        proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=_TERMINATE_GRACE_SECONDS)
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


def terminate_agent_process(agent: Optional[PresetSessionProcess]) -> None:
    """Twin of `_terminate_process` driven by pid, because the caller (`preset stop`) never owned the process."""
    if agent is None or not process_alive(agent):
        return
    agent_pid = agent.pid
    if IS_WINDOWS:
        _terminate_windows_process_tree(agent_pid)
        return
    _terminate_processes(_process_descendants(agent_pid).values())
    with suppress(OSError):
        os.killpg(agent_pid, signal.SIGTERM)  # pyright: ignore[reportAttributeAccessIssue]
    for _ in range(_TERMINATE_GRACE_SECONDS * 10):
        if not pid_running(agent_pid):
            return
        time.sleep(0.1)
    with suppress(OSError):
        os.killpg(agent_pid, signal.SIGKILL)  # pyright: ignore[reportAttributeAccessIssue]


def _process_descendants(pid: int) -> dict[int, psutil.Process]:
    try:
        processes = psutil.Process(pid).children(recursive=True)
    except psutil.NoSuchProcess:
        return {}
    return {process.pid: process for process in processes}


async def _watch_process_descendants(pid: int, descendants: dict[int, psutil.Process]) -> None:
    while True:
        descendants.update(_process_descendants(pid))
        if not pid_running(pid):
            return
        await asyncio.sleep(0.05)


def _terminate_processes(processes: Iterable[psutil.Process]) -> None:
    processes = list(processes)
    for process in processes:
        with suppress(psutil.NoSuchProcess):
            process.terminate()
    _, alive = psutil.wait_procs(processes, timeout=_TERMINATE_GRACE_SECONDS)
    for process in alive:
        with suppress(psutil.NoSuchProcess):
            process.kill()
    psutil.wait_procs(alive, timeout=_TERMINATE_GRACE_SECONDS)


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


def _get_report_json_schema() -> dict[str, Any]:
    """The one shape the API can enforce: a single object, no union, only
    `success` required. `AnyPresetAgentResult` enforces the rest at parse."""
    success = PresetAgentSuccess.model_json_schema()
    failure = PresetAgentFailure.model_json_schema()
    return {
        "type": "object",
        "properties": {
            **success["properties"],
            **failure["properties"],
            # Each outcome fixes its own value; only the merged shape offers both.
            "success": {"type": "boolean"},
        },
        "required": ["success"],
        "additionalProperties": False,
        "$defs": {**success.get("$defs", {}), **failure.get("$defs", {})},
    }
