import asyncio
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional, Sequence

import psutil
from rich.text import Text

from dstack._internal.cli.utils.common import console
from dstack._internal.compat import IS_WINDOWS
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.endpoint_agent import AGENT_FINAL_REPORT_JSON_SCHEMA
from dstack.api import Client

_SKILL_NAMES = ("dstack", "dstack-prototyping")
_PROGRESS_FILENAME = "progress.jsonl"
_SUBMISSIONS_FILENAME = "submissions.jsonl"
_BENCHMARKS_FILENAME = "benchmarks.jsonl"
_FINAL_REPORT_FILENAME = "final_report.json"
_PROGRESS_ENV = "DSTACK_ENDPOINT_PROGRESS_LOG"
_REDACTION = "[redacted]"
_CLAUDE_TOOLS = "Bash,Read,Write,Edit,WebFetch,WebSearch,StructuredOutput"
_CLAUDE_EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
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


@dataclass(frozen=True)
class EndpointAgentWorkspace:
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
    def submissions_path(self) -> Path:
        return self.path / _SUBMISSIONS_FILENAME

    @property
    def benchmarks_path(self) -> Path:
        return self.path / _BENCHMARKS_FILENAME

    @property
    def final_report_path(self) -> Path:
        return self.path / _FINAL_REPORT_FILENAME

    @property
    def stdout_path(self) -> Path:
        return self.path / "agent_stdout.jsonl"

    @property
    def stderr_path(self) -> Path:
        return self.path / "agent_stderr.jsonl"


@dataclass(frozen=True)
class ClaudeAuth:
    api_key: Optional[str]
    executable: str
    effort: Optional[str]
    model: str
    use_existing: bool


@dataclass
class EndpointAgentProcessOutput:
    report_data: Optional[dict[str, Any]] = None
    error: Optional[str] = None


@contextmanager
def endpoint_agent_workspace() -> Iterator[EndpointAgentWorkspace]:
    with tempfile.TemporaryDirectory(prefix="dpe-", dir=_get_short_temp_dir()) as directory:
        root = Path(directory)
        _validate_control_socket_path(root)
        workspace = EndpointAgentWorkspace(path=root / "w", dstack_home=root / "h")
        _prepare_workspace(workspace)
        yield workspace


def get_claude_auth() -> ClaudeAuth:
    api_key = os.getenv("DSTACK_AGENT_ANTHROPIC_API_KEY") or None
    use_existing = _get_bool_env("DSTACK_AGENT_CLAUDE_USE_EXISTING_AUTH")
    if api_key and use_existing:
        raise CLIError(
            "DSTACK_AGENT_ANTHROPIC_API_KEY and "
            "DSTACK_AGENT_CLAUDE_USE_EXISTING_AUTH cannot both be set"
        )
    if not api_key and not use_existing:
        raise CLIError(
            "DSTACK_AGENT_ANTHROPIC_API_KEY is not set. Set it or opt in to existing "
            "Claude CLI auth with DSTACK_AGENT_CLAUDE_USE_EXISTING_AUTH=1"
        )
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
        use_existing=use_existing,
    )


def build_endpoint_agent_env(
    *,
    api: Client,
    endpoint_env: dict[str, str],
    auth: ClaudeAuth,
    workspace: EndpointAgentWorkspace,
    token: str,
) -> dict[str, str]:
    env = {name: value for name in _INHERITED_ENV_NAMES if (value := os.getenv(name))}
    env.update(endpoint_env)
    if IS_WINDOWS:
        env.update(
            {name: value for name in _WINDOWS_INHERITED_ENV_NAMES if (value := os.getenv(name))}
        )
    env["PATH"] = os.pathsep.join([str(workspace.bin_path), env.get("PATH", "")])
    env["DSTACK_SERVER_URL"] = api.client.base_url
    env["DSTACK_PROJECT"] = api.project
    env["DSTACK_TOKEN"] = token
    env["DSTACK_ENDPOINT_SERVER_URL"] = api.client.base_url
    env["DSTACK_ENDPOINT_BEARER_TOKEN"] = token
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


async def run_endpoint_agent(
    *,
    prompt: str,
    env: dict[str, str],
    workspace: EndpointAgentWorkspace,
    auth: ClaudeAuth,
    redacted_values: Sequence[str],
) -> EndpointAgentProcessOutput:
    command = _prepare_subprocess_command(_build_claude_command(auth=auth))
    progress_tailer = _ProgressTailer(
        path=workspace.progress_path,
        redacted_values=redacted_values,
    )
    progress_task = asyncio.create_task(progress_tailer.run())
    proc: Optional[asyncio.subprocess.Process] = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=workspace.path,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=not IS_WINDOWS,
        )
        assert proc.stdin is not None
        assert proc.stdout is not None
        assert proc.stderr is not None
        proc.stdin.write(prompt.encode())
        with suppress(BrokenPipeError, ConnectionResetError):
            await proc.stdin.drain()
        proc.stdin.close()
        stdout_task = asyncio.create_task(
            _read_process_stream(
                stream=proc.stdout,
                path=workspace.stdout_path,
                parse_result=True,
                redacted_values=redacted_values,
            )
        )
        stderr_task = asyncio.create_task(
            _read_process_stream(
                stream=proc.stderr,
                path=workspace.stderr_path,
                parse_result=False,
                redacted_values=redacted_values,
            )
        )
        stdout_output, stderr_output, returncode = await asyncio.gather(
            stdout_task,
            stderr_task,
            proc.wait(),
        )
    except BaseException:
        if proc is not None and proc.returncode is None:
            await _terminate_process(proc)
        raise
    finally:
        progress_task.cancel()
        with suppress(asyncio.CancelledError):
            await progress_task
        progress_tailer.flush()

    output = stdout_output
    if output.report_data is None:
        output.report_data = stderr_output.report_data
    if output.error is None:
        output.error = stderr_output.error
    if output.report_data is None and returncode != 0:
        output.error = output.error or f"Claude exited with return code {returncode}"
    return output


def print_endpoint_progress(message: str) -> None:
    timestamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    console.print(
        Text(f"[{timestamp}]", style="log.time"),
        Text(message.rstrip("\r\n"), style="log.message"),
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
        value = value.replace(redacted_value, _REDACTION)
    return value


def _get_bool_env(name: str) -> bool:
    value = os.getenv(name)
    if value is None:
        return False
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise CLIError(f"{name} must be a boolean")


def _validate_control_socket_path(build_root: Path) -> None:
    if IS_WINDOWS:
        return
    path = build_root / "h" / ".dstack" / "ssh" / f"{'x' * _MAX_RUN_NAME_LENGTH}.control.sock"
    if len(os.fsencode(path)) > _MAX_UNIX_SOCKET_PATH_BYTES:
        raise CLIError(f"Temporary path is too long for an SSH control socket: {build_root}")


def _prepare_workspace(workspace: EndpointAgentWorkspace) -> None:
    workspace.path.mkdir(mode=0o700, parents=True, exist_ok=False)
    workspace.dstack_home.mkdir(mode=0o700)
    workspace.temp_path.mkdir(mode=0o700)
    for path in [
        workspace.progress_path,
        workspace.submissions_path,
        workspace.benchmarks_path,
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

print("Endpoint preset creation could not find the {command} executable.", file=sys.stderr)
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
            raise CLIError(f"Missing endpoint agent skill: {skill_name}")
        shutil.copytree(source, target_dir / skill_name)


def _get_skills_dir() -> Path:
    source_path = Path(__file__).resolve()
    candidates = (
        source_path.parents[2] / "core" / "resources" / "endpoint_agent" / "skills",
        source_path.parents[5] / "skills",
    )
    for candidate in candidates:
        if (candidate / "dstack" / "SKILL.md").is_file():
            return candidate
    raise CLIError("Could not find packaged dstack skills")


def _build_claude_command(*, auth: ClaudeAuth) -> list[str]:
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
    if auth.use_existing:
        command[2:2] = ["--setting-sources", "project,local"]
    else:
        command[2:2] = ["--bare"]
    if auth.effort is not None:
        command[2:2] = ["--effort", auth.effort]
    return command


def _prepare_subprocess_command(command: list[str]) -> list[str]:
    if not IS_WINDOWS or Path(command[0]).suffix.lower() not in {".bat", ".cmd"}:
        return command
    comspec = os.getenv("COMSPEC") or shutil.which("cmd.exe")
    if comspec is None:
        raise CLIError("Cannot run the Claude batch launcher because cmd.exe was not found")
    return [comspec, "/d", "/s", "/c", subprocess.list2cmdline(command)]


async def _read_process_stream(
    *,
    stream: asyncio.StreamReader,
    path: Path,
    parse_result: bool,
    redacted_values: Sequence[str],
) -> EndpointAgentProcessOutput:
    output = EndpointAgentProcessOutput()
    with path.open("a", encoding="utf-8") as f:
        while True:
            line = await stream.readline()
            if not line:
                return output
            text = line.decode(errors="replace")
            f.write(redact(text, redacted_values))
            f.flush()
            if not parse_result:
                continue
            try:
                message = json.loads(text)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict) or message.get("type") != "result":
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
    if hasattr(os, "killpg"):
        with suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)
    else:
        proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=3)
    except asyncio.TimeoutError:
        if hasattr(os, "killpg"):
            with suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
        await proc.wait()


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


class _ProgressTailer:
    def __init__(self, *, path: Path, redacted_values: Sequence[str]) -> None:
        self._path = path
        self._redacted_values = redacted_values
        self._offset = 0

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
        for line in lines:
            message = _parse_progress(line)
            if message is not None:
                print_endpoint_progress(redact(message, self._redacted_values))


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
