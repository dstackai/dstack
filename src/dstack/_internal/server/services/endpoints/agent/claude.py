import asyncio
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, Sequence
from uuid import UUID

import yaml
from pydantic import ValidationError

from dstack._internal.core.models.config import GlobalConfig, ProjectConfig
from dstack._internal.core.models.endpoints import EndpointConfiguration
from dstack._internal.server import settings
from dstack._internal.server.models import EndpointModel, ProjectModel
from dstack._internal.server.schemas.runner import LogEvent
from dstack._internal.server.services import logs as logs_services
from dstack._internal.server.services.endpoints.agent import (
    AgentPlan,
    AgentProvisioningResult,
    AgentService,
    get_effective_max_agent_budget,
)
from dstack._internal.server.services.endpoints.agent.report import (
    AGENT_FINAL_REPORT_JSON_SCHEMA,
    AgentFinalReport,
)
from dstack._internal.server.services.pipelines import PipelineHinterProtocol
from dstack._internal.utils.common import get_milliseconds_since_epoch, run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

_RESOURCE_DIR = Path(__file__).parent / "resources"
_PROMPT_RESOURCE_NAMES = [
    "system_prompt.md",
    "dstack_cli_and_service_authoring.md",
    "recipes_guide.md",
    "deployment_harness.md",
]
_INHERITED_ENV_NAMES = [
    "PATH",
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
]
_REDACTION = "[redacted]"
_MAX_CAPTURED_OUTPUT_CHARS = 20_000
_MAX_AGENT_LOG_MESSAGE_CHARS = 4_000
_MAX_TOOL_RESULT_LOG_PREVIEW_CHARS = 1_200
_MAX_TOOL_RESULT_LOG_PREVIEW_LINES = 30
_AGENT_LOG_BATCH_SIZE = 1
_CLAUDE_AGENT_TOOLS = "Bash,Read,Write,Edit,WebFetch,WebSearch,StructuredOutput"


@dataclass(frozen=True)
class _AgentRunnerResult:
    report: Optional[AgentFinalReport] = None
    error: Optional[str] = None


@dataclass
class _AgentProcessOutput:
    report_data: Optional[dict[str, Any]] = None
    result_error: Optional[str] = None
    stdout_tail: str = ""


class ClaudeAgentService(AgentService):
    def __init__(
        self,
        runner: Optional[
            Callable[["_AgentWorkspace", dict[str, Any]], Awaitable[_AgentRunnerResult]]
        ] = None,
        workspace_base_dir: Path = settings.SERVER_DATA_DIR_PATH / "endpoint_agent_runs",
    ) -> None:
        self._runner = runner or _run_agent_in_subprocess
        self._workspace_base_dir = workspace_base_dir

    def is_enabled(self) -> bool:
        return get_claude_agent_unavailable_reason() is None

    def get_plan(self) -> AgentPlan:
        return AgentPlan(model=settings.AGENT_ANTHROPIC_MODEL)

    async def provision_endpoint(
        self,
        endpoint_model: EndpointModel,
        pipeline_hinter: PipelineHinterProtocol,
    ) -> AgentProvisioningResult:
        unavailable_reason = get_claude_agent_unavailable_reason()
        if unavailable_reason is not None:
            return AgentProvisioningResult(error=unavailable_reason)

        try:
            workspace = _prepare_workspace(
                endpoint_model=endpoint_model,
                workspace_base_dir=self._workspace_base_dir,
            )
        except Exception as e:
            logger.warning("Failed to prepare endpoint agent workspace: %s", e, exc_info=True)
            return AgentProvisioningResult(
                error=f"Failed to prepare endpoint agent workspace: {e}"
            )

        runner_result = await self._runner(workspace, _build_agent_request(workspace))
        if runner_result.error is not None:
            workspace.artifacts.record_error(runner_result.error)
            return AgentProvisioningResult(error=runner_result.error)
        report = runner_result.report
        if report is None:
            workspace.artifacts.record_error("Server agent did not return a verification report")
            return AgentProvisioningResult(
                error="Server agent did not return a verification report"
            )
        workspace.artifacts.record_report(report)

        logger.info(
            "Endpoint agent finished for endpoint %s: success=%s run_id=%s run_name=%s",
            endpoint_model.name,
            report.success,
            report.run_id,
            report.run_name,
        )
        return AgentProvisioningResult(
            run_id=report.run_id,
            run_name=report.run_name,
            final_report=report,
        )


def get_claude_agent_unavailable_reason() -> Optional[str]:
    if not settings.AGENT_ANTHROPIC_API_KEY:
        return "DSTACK_AGENT_ANTHROPIC_API_KEY is not set."
    if _get_claude_executable() is None:
        if settings.AGENT_CLAUDE_PATH is not None:
            return (
                "DSTACK_AGENT_CLAUDE_PATH does not resolve to an executable: "
                f"{settings.AGENT_CLAUDE_PATH}"
            )
        return (
            "server agent runtime requires the claude executable in PATH or "
            "DSTACK_AGENT_CLAUDE_PATH."
        )
    return None


class _AgentWorkspace:
    def __init__(
        self,
        *,
        root_dir: Path,
        home_dir: Path,
        work_dir: Path,
        trace_path: Optional[Path],
        env: dict[str, str],
        redacted_values: Sequence[str],
        endpoint_name: str,
        model: str,
        max_agent_budget: Optional[float],
        endpoint_constraints: str = "",
        max_price: Optional[float] = None,
        spot_policy: Optional[str] = None,
        log_writer: Optional["_AgentLogWriter"] = None,
    ) -> None:
        self.root_dir = root_dir
        self.home_dir = home_dir
        self.work_dir = work_dir
        self.trace_path = trace_path
        self.env = env
        self.redacted_values = tuple(redacted_values)
        self.endpoint_name = endpoint_name
        self.model = model
        self.max_agent_budget = max_agent_budget
        self.endpoint_constraints = endpoint_constraints
        self.max_price = max_price
        self.spot_policy = spot_policy
        self.log_writer = log_writer
        self.artifacts = _AgentArtifactRecorder(self)


class _AgentLogWriter:
    def __init__(
        self,
        *,
        project: ProjectModel,
        endpoint_id: UUID,
        endpoint_name: str,
    ) -> None:
        self._project = project
        self._endpoint_id = endpoint_id
        self._endpoint_name = endpoint_name
        self._buffer: list[LogEvent] = []

    async def write(self, message: str) -> None:
        message = _truncate_log_message(message)
        if not message.endswith("\n"):
            message += "\n"
        self._buffer.append(
            LogEvent(
                timestamp=get_milliseconds_since_epoch(),
                message=message.encode(),
            )
        )
        if len(self._buffer) >= _AGENT_LOG_BATCH_SIZE:
            await self.flush()

    async def flush(self) -> None:
        if not self._buffer:
            return
        events = self._buffer
        self._buffer = []
        try:
            await run_async(
                logs_services.write_logs,
                project=self._project,
                run_name=self._endpoint_name,
                job_submission_id=self._endpoint_id,
                runner_logs=[],
                job_logs=events,
            )
        except Exception:
            logger.warning(
                "Failed to write endpoint agent logs for endpoint %s",
                self._endpoint_name,
                exc_info=True,
            )


def _prepare_workspace(
    *,
    endpoint_model: EndpointModel,
    workspace_base_dir: Path,
) -> _AgentWorkspace:
    configuration = EndpointConfiguration.__response__.parse_raw(endpoint_model.configuration)

    root_dir = workspace_base_dir / str(endpoint_model.id)
    home_dir = root_dir / "home"
    work_dir = root_dir / "workspace"
    dstack_dir = home_dir / ".dstack"
    work_dir.mkdir(parents=True, exist_ok=True)
    dstack_dir.mkdir(parents=True, exist_ok=True)
    token = endpoint_model.user.token.get_plaintext_or_error()
    _write_cli_config(
        dstack_dir=dstack_dir,
        project_name=endpoint_model.project.name,
        server_url=settings.SERVER_URL,
        token=token,
    )

    endpoint_env = configuration.env.as_dict()
    env = _build_agent_env(
        home_dir=home_dir,
        project_name=endpoint_model.project.name,
        endpoint_env=endpoint_env,
    )
    redacted_values = _get_redacted_values(
        [
            token,
            settings.AGENT_ANTHROPIC_API_KEY or "",
            *endpoint_env.values(),
            *_get_sensitive_inherited_env_values(env),
        ]
    )
    trace_path = root_dir / "trace.jsonl" if _is_debug_trace_enabled() else None
    workspace = _AgentWorkspace(
        root_dir=root_dir,
        home_dir=home_dir,
        work_dir=work_dir,
        trace_path=trace_path,
        env=env,
        redacted_values=redacted_values,
        endpoint_name=endpoint_model.name,
        model=configuration.model,
        max_agent_budget=get_effective_max_agent_budget(configuration),
        endpoint_constraints=_format_endpoint_constraints(configuration, endpoint_env),
        max_price=configuration.max_price,
        spot_policy=configuration.spot_policy.value if configuration.spot_policy else None,
        log_writer=_AgentLogWriter(
            project=endpoint_model.project,
            endpoint_id=endpoint_model.id,
            endpoint_name=endpoint_model.name,
        ),
    )
    workspace.artifacts.initialize()
    return workspace


class _AgentArtifactRecorder:
    def __init__(self, workspace: _AgentWorkspace) -> None:
        self._workspace = workspace
        self._command_counter = 0

    def initialize(self) -> None:
        self._workspace.work_dir.mkdir(parents=True, exist_ok=True)
        self._update_agent_state(phase="starting")
        for filename in ["sources.jsonl", "candidates.jsonl", "commands.jsonl"]:
            (self._workspace.work_dir / filename).touch(exist_ok=True)
        hardware_reasoning_path = self._workspace.work_dir / "hardware_reasoning.md"
        if not hardware_reasoning_path.exists():
            hardware_reasoning_path.write_text(
                (
                    "# Hardware Reasoning\n\n"
                    "The endpoint agent should update this file with the model size,\n"
                    "serving framework, resource estimate, offer/fleet choice, and\n"
                    "why the selected hardware is credible.\n"
                ),
                encoding="utf-8",
            )

    def mark_running(self) -> None:
        self._update_agent_state(phase="running")

    def record_report(self, report: AgentFinalReport) -> None:
        (self._workspace.work_dir / "final_report.json").write_text(
            json.dumps(
                _redact(report.dict(), self._workspace.redacted_values),
                default=str,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        self._update_agent_state(phase="success" if report.success else "failure")

    def record_error(self, error: str) -> None:
        data = {
            "success": False,
            "failure_summary": error,
            "recorded_at": _utcnow_iso(),
        }
        (self._workspace.work_dir / "agent_error.json").write_text(
            json.dumps(_redact(data, self._workspace.redacted_values), indent=2) + "\n",
            encoding="utf-8",
        )
        self._update_agent_state(phase="failure")

    def record_stream_message(self, message: dict[str, Any]) -> None:
        self._record_bash_tool_uses(message)
        self._record_tool_results(message)

    def _update_agent_state(self, phase: str) -> None:
        path = self._workspace.work_dir / "agent_state.json"
        state: dict[str, Any] = {}
        if path.exists():
            try:
                parsed = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                parsed = {}
            if isinstance(parsed, dict):
                state.update(parsed)
        now = _utcnow_iso()
        state.update(
            {
                "endpoint_name": self._workspace.endpoint_name,
                "model": self._workspace.model,
                "phase": phase,
                "max_agent_budget": self._workspace.max_agent_budget,
                "max_hourly_price": self._workspace.max_price,
                "spot_policy": self._workspace.spot_policy,
                "updated_at": now,
            }
        )
        state.setdefault("started_at", now)
        path.write_text(
            json.dumps(_redact(state, self._workspace.redacted_values), indent=2) + "\n",
            encoding="utf-8",
        )

    def _record_bash_tool_uses(self, message: dict[str, Any]) -> None:
        if message.get("type") != "assistant":
            return
        claude_message = message.get("message")
        if not isinstance(claude_message, dict):
            return
        for item in claude_message.get("content", []):
            if not isinstance(item, dict):
                continue
            if item.get("type") != "tool_use" or item.get("name") != "Bash":
                continue
            tool_input = item.get("input")
            if not isinstance(tool_input, dict):
                continue
            command = tool_input.get("command")
            if not isinstance(command, str) or not command.strip():
                continue
            record = {
                "event": "tool_use",
                "timestamp": _utcnow_iso(),
                "tool_use_id": item.get("id"),
                "description": tool_input.get("description"),
                "command": command,
            }
            self._append_jsonl("commands.jsonl", record)

    def _record_tool_results(self, message: dict[str, Any]) -> None:
        if message.get("type") != "user":
            return
        claude_message = message.get("message")
        if not isinstance(claude_message, dict):
            return
        for item in claude_message.get("content", []):
            if not isinstance(item, dict) or item.get("type") != "tool_result":
                continue
            content = item.get("content")
            output_path = None
            if isinstance(content, str) and content.strip():
                output_path = self._write_command_output(content)
            record = {
                "event": "tool_result",
                "timestamp": _utcnow_iso(),
                "tool_use_id": item.get("tool_use_id") or message.get("parent_tool_use_id"),
                "is_error": bool(item.get("is_error")),
                "output_path": output_path,
            }
            self._append_jsonl("commands.jsonl", record)

    def _write_command_output(self, content: str) -> str:
        self._command_counter += 1
        output_dir = self._workspace.work_dir / "command-output"
        output_dir.mkdir(parents=True, exist_ok=True)
        relative_path = Path("command-output") / f"{self._command_counter:04d}.txt"
        output_path = self._workspace.work_dir / relative_path
        output_path.write_text(
            _redact(content, self._workspace.redacted_values),
            encoding="utf-8",
        )
        return relative_path.as_posix()

    def _append_jsonl(self, filename: str, record: dict[str, Any]) -> None:
        path = self._workspace.work_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(_redact(record, self._workspace.redacted_values), default=str) + "\n"
            )


def _write_cli_config(
    *,
    dstack_dir: Path,
    project_name: str,
    server_url: str,
    token: str,
) -> None:
    config = GlobalConfig(
        projects=[
            ProjectConfig(
                name=project_name,
                url=server_url,
                token=token,
                default=True,
            )
        ]
    )
    (dstack_dir / "config.yml").write_text(
        yaml.safe_dump(json.loads(config.json()), sort_keys=False),
        encoding="utf-8",
    )


def _build_agent_env(
    *,
    home_dir: Path,
    project_name: str,
    endpoint_env: dict[str, str],
) -> dict[str, str]:
    env = {name: value for name in _INHERITED_ENV_NAMES if (value := os.environ.get(name))}
    env.update(
        {
            "ANTHROPIC_API_KEY": settings.AGENT_ANTHROPIC_API_KEY or "",
            "HOME": str(home_dir),
            "DSTACK_PROJECT": project_name,
        }
    )
    env.update(endpoint_env)
    return env


def _build_agent_request(workspace: _AgentWorkspace) -> dict[str, Any]:
    return {
        "prompt": _build_prompt(workspace),
        "cwd": str(workspace.work_dir),
        "env": workspace.env,
        "trace_path": str(workspace.trace_path) if workspace.trace_path is not None else None,
        "redacted_values": list(workspace.redacted_values),
        "options": {
            "tools": _CLAUDE_AGENT_TOOLS,
            "allowed_tools": _CLAUDE_AGENT_TOOLS,
            "disallowed_tools": "Task,NotebookEdit",
            "model": settings.AGENT_ANTHROPIC_MODEL,
            "max_turns": None,
            "max_budget": workspace.max_agent_budget,
            "json_schema": AGENT_FINAL_REPORT_JSON_SCHEMA,
        },
    }


def _build_prompt(workspace: _AgentWorkspace) -> str:
    return f"""Deploy endpoint {workspace.endpoint_name!r} for model {workspace.model!r}.

Use the real `dstack` CLI available in this process. Do not use any custom dstack APIs
or wait for any server-side helper tool. The embedded guidance below is the dstack and
dstack-development playbook for this run.

{workspace.endpoint_constraints}

Required final service:
- service YAML type: service
- service YAML must set `model: {workspace.model}`
- submit runs detached with `dstack apply -f <file> -y -d`
- use concise, unique run names that are useful for debugging
- the successful final report must include the verified service run `run_id`

{_load_prompt_resources()}

When you have a terminal result, write `final_report.json` in the workspace with the
same fields requested by the JSON schema, then return only the structured final report.
"""


def _load_prompt_resources() -> str:
    return "\n\n".join(
        (_RESOURCE_DIR / resource_name).read_text(encoding="utf-8").strip()
        for resource_name in _PROMPT_RESOURCE_NAMES
    )


def _format_endpoint_constraints(
    configuration: EndpointConfiguration,
    endpoint_env: dict[str, str],
) -> str:
    lines = [
        "Binding endpoint constraints:",
        "- Every `dstack offer`, `dstack apply` preview, and submitted service must honor these constraints.",
        "- Do not submit a service if the plan violates these constraints.",
    ]
    cli_flags = []
    if configuration.max_price is not None:
        lines.append(f"- max_price: {configuration.max_price}")
        cli_flags.extend(["--max-price", str(configuration.max_price)])
    if configuration.spot_policy is not None:
        lines.append(f"- spot_policy: {configuration.spot_policy.value}")
        if configuration.spot_policy.value == "spot":
            cli_flags.append("--spot")
        elif configuration.spot_policy.value == "on-demand":
            cli_flags.append("--on-demand")
        else:
            cli_flags.append("--spot-auto")
    for field, flag in [
        ("backends", "--backend"),
        ("regions", "--region"),
        ("instance_types", "--instance-type"),
        ("fleets", "--fleet"),
    ]:
        values = getattr(configuration, field)
        if not values:
            continue
        formatted_values = [_format_constraint_value(value) for value in values]
        lines.append(f"- {field}: {', '.join(formatted_values)}")
        for value in formatted_values:
            cli_flags.extend([flag, value])
    for field in ["availability_zones", "instances"]:
        values = getattr(configuration, field)
        if not values:
            continue
        formatted_values = [_format_constraint_value(value) for value in values]
        lines.append(f"- {field}: {', '.join(formatted_values)}")
    if configuration.creation_policy is not None:
        lines.append(f"- creation_policy: {configuration.creation_policy.value}")
        if configuration.creation_policy.value == "reuse":
            cli_flags.append("--reuse")
    if cli_flags:
        lines.append(f"- Reuse these CLI flags where applicable: {' '.join(cli_flags)}")
    else:
        lines.append("- No explicit profile constraints were set.")
    if endpoint_env:
        lines.append(
            f"- Endpoint env keys available in the agent environment: {', '.join(endpoint_env)}"
        )
    else:
        lines.append("- Endpoint env keys: none")
    return "\n".join(lines)


def _format_constraint_value(value: Any) -> str:
    if hasattr(value, "name") and getattr(value, "project", None) is None:
        return str(value.name)
    if hasattr(value, "json"):
        return json.dumps(json.loads(value.json()), sort_keys=True)
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


async def _run_agent_in_subprocess(
    workspace: _AgentWorkspace,
    request: dict[str, Any],
) -> _AgentRunnerResult:
    cmd = _build_claude_command(request)
    await _write_agent_log(
        workspace,
        _format_agent_start_log(request),
    )
    workspace.artifacts.mark_running()
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=workspace.work_dir,
        env=request["env"],
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.stdout is not None
    assert proc.stderr is not None
    stdout_task = asyncio.create_task(_read_agent_stdout(proc.stdout, workspace))
    stderr_task = asyncio.create_task(_read_agent_stderr(proc.stderr, workspace))
    stdout_output, stderr_output, returncode = await asyncio.gather(
        stdout_task,
        stderr_task,
        proc.wait(),
    )
    process_output = _merge_process_outputs(stdout_output, stderr_output)
    _write_trace_record(
        workspace,
        {
            "type": "agent-process",
            "returncode": returncode,
        },
    )
    await _write_agent_log(workspace, f"Server agent process exited with code {returncode}")
    await _flush_agent_logs(workspace)
    if process_output.report_data is None:
        process_output.report_data = _load_final_report_artifact(workspace)
    if process_output.report_data is None:
        if process_output.result_error is not None:
            return _AgentRunnerResult(
                error="Server agent failed before returning a verification report"
            )
        if returncode not in (0, None):
            return _AgentRunnerResult(
                error=(
                    "Server agent process exited without a verification report "
                    f"(return code {returncode})"
                )
            )
        return _AgentRunnerResult(
            error="Server agent process exited without a verification report"
        )
    try:
        return _AgentRunnerResult(report=AgentFinalReport.parse_obj(process_output.report_data))
    except ValidationError as e:
        return _AgentRunnerResult(
            error=f"Server agent returned an invalid verification report: {e}"
        )


def _build_claude_command(request: dict[str, Any]) -> list[str]:
    options = request["options"]
    cmd = [
        _get_claude_executable() or "claude",
        "-p",
        "--bare",
        "--output-format",
        "stream-json",
        "--verbose",
        "--tools",
        options.get("tools", "default"),
        "--allowedTools",
        options["allowed_tools"],
        "--disallowedTools",
        options["disallowed_tools"],
        "--permission-mode",
        "bypassPermissions",
        "--model",
        options["model"],
        "--json-schema",
        json.dumps(options["json_schema"]),
        request["prompt"],
    ]
    if options["max_turns"] is not None:
        cmd[2:2] = ["--max-turns", str(options["max_turns"])]
    if options["max_budget"] is not None:
        cmd[2:2] = ["--max-budget-usd", str(options["max_budget"])]
    return cmd


def _get_claude_executable() -> Optional[str]:
    if settings.AGENT_CLAUDE_PATH is not None:
        return shutil.which(settings.AGENT_CLAUDE_PATH)
    return shutil.which("claude")


async def _read_agent_stdout(
    stream: asyncio.StreamReader,
    workspace: _AgentWorkspace,
) -> _AgentProcessOutput:
    return await _read_agent_stream(stream, workspace, stream_name="stdout")


async def _read_agent_stderr(
    stream: asyncio.StreamReader,
    workspace: _AgentWorkspace,
) -> _AgentProcessOutput:
    return await _read_agent_stream(stream, workspace, stream_name="stderr")


async def _read_agent_stream(
    stream: asyncio.StreamReader,
    workspace: _AgentWorkspace,
    stream_name: str,
) -> _AgentProcessOutput:
    output = _AgentProcessOutput()
    while True:
        line_bytes = await stream.readline()
        if not line_bytes:
            return output
        line = line_bytes.decode(errors="replace")
        output.stdout_tail = _append_bounded_output(output.stdout_tail, line)
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            message = {"type": "raw-output", "stream": stream_name, "line": line.rstrip("\r\n")}
            _write_trace_record(workspace, message)
            await _write_agent_log_if_present(workspace, message)
            continue
        if stream_name != "stdout":
            message.setdefault("stream", stream_name)
        _write_trace_record(workspace, message)
        workspace.artifacts.record_stream_message(message)
        _update_agent_process_output(output, message)
        await _write_agent_log_if_present(workspace, message)


def _update_agent_process_output(
    output: _AgentProcessOutput,
    message: dict[str, Any],
) -> None:
    if message.get("type") != "result":
        return
    if message.get("is_error"):
        output.result_error = message.get("result") or "Claude agent failed"
    structured_output = message.get("structured_output")
    if isinstance(structured_output, dict):
        output.report_data = structured_output
        return
    report_data = _parse_report_json(message.get("result"))
    if report_data is not None:
        output.report_data = report_data


def _append_bounded_output(existing: str, addition: str) -> str:
    combined = existing + addition
    if len(combined) <= _MAX_CAPTURED_OUTPUT_CHARS:
        return combined
    return combined[-_MAX_CAPTURED_OUTPUT_CHARS:]


def _merge_process_outputs(*outputs: _AgentProcessOutput) -> _AgentProcessOutput:
    merged = _AgentProcessOutput()
    for output in outputs:
        if output.report_data is not None:
            merged.report_data = output.report_data
        if output.result_error is not None:
            merged.result_error = output.result_error
        merged.stdout_tail = _append_bounded_output(merged.stdout_tail, output.stdout_tail)
    return merged


async def _write_agent_log_if_present(
    workspace: _AgentWorkspace,
    message: dict[str, Any],
) -> None:
    log_message = _format_agent_log_message(message)
    if log_message is not None:
        await _write_agent_log(workspace, log_message)


async def _write_agent_log(workspace: _AgentWorkspace, message: str) -> None:
    if workspace.log_writer is None:
        return
    message = _redact(message, workspace.redacted_values)
    await workspace.log_writer.write(message)


async def _flush_agent_logs(workspace: _AgentWorkspace) -> None:
    if workspace.log_writer is None:
        return
    await workspace.log_writer.flush()


def _format_agent_start_log(request: dict[str, Any]) -> str:
    options = request["options"]
    parts = [f"Starting server agent ({options['model']})"]
    if options["max_budget"] is not None:
        parts.append(f"max budget ${options['max_budget']}")
    cwd = request.get("cwd")
    if cwd:
        parts.append(f"workspace {cwd}")
    return ", ".join(parts)


def _format_agent_log_message(message: dict[str, Any]) -> Optional[str]:
    message_type = message.get("type")
    if message_type == "system" and message.get("subtype") == "init":
        model = message.get("model")
        version = message.get("claude_code_version")
        details = ", ".join(
            str(v) for v in [model, f"Claude Code {version}" if version else None] if v
        )
        return f"Server agent initialized ({details})" if details else "Server agent initialized"
    if message_type == "assistant":
        return _format_assistant_message_log(message.get("message"))
    if message_type == "user":
        return _format_user_message_log(message.get("message"))
    if message_type == "result":
        if message.get("is_error"):
            result = message.get("result")
            if isinstance(result, str) and result.strip():
                return f"Server agent failed: {_truncate_log_message(result.strip())}"
            return "Server agent failed"
        return "Server agent finished"
    if message_type == "raw-output":
        line = message.get("line")
        if isinstance(line, str) and line.strip():
            prefix = "Agent stderr" if message.get("stream") == "stderr" else "Agent output"
            return f"{prefix}: {line.strip()}"
    return None


def _format_assistant_message_log(message: Any) -> Optional[str]:
    if not isinstance(message, dict):
        return None
    lines = []
    for item in message.get("content", []):
        if not isinstance(item, dict):
            continue
        if item.get("type") == "tool_use":
            name = item.get("name") or "tool"
            tool_input = item.get("input")
            description = None
            command = None
            if isinstance(tool_input, dict):
                description = tool_input.get("description")
                command = tool_input.get("command")
            if isinstance(description, str) and description.strip():
                lines.append(f"Agent tool: {name} ({description.strip()})")
            else:
                lines.append(f"Agent tool: {name}")
            if isinstance(command, str) and command.strip():
                lines.append(f"$ {command.strip()}")
        elif item.get("type") == "text" and isinstance(item.get("text"), str):
            text = item["text"].strip()
            if text:
                lines.append(text)
    if not lines:
        return None
    return "\n".join(lines)


def _format_user_message_log(message: Any) -> Optional[str]:
    if not isinstance(message, dict):
        return None
    lines = []
    for item in message.get("content", []):
        if not isinstance(item, dict) or item.get("type") != "tool_result":
            continue
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        prefix = "Tool error" if item.get("is_error") else "Tool output"
        lines.append(_format_tool_result_log(prefix, content))
    if not lines:
        return None
    return "\n\n".join(lines)


def _format_tool_result_log(prefix: str, content: str) -> str:
    stripped = content.strip()
    result_lines = stripped.splitlines()
    if (
        len(stripped) <= _MAX_TOOL_RESULT_LOG_PREVIEW_CHARS
        and len(result_lines) <= _MAX_TOOL_RESULT_LOG_PREVIEW_LINES
    ):
        return f"{prefix}:\n{stripped}"

    preview_lines = result_lines[:_MAX_TOOL_RESULT_LOG_PREVIEW_LINES]
    preview = "\n".join(preview_lines)
    if len(preview) > _MAX_TOOL_RESULT_LOG_PREVIEW_CHARS:
        preview = preview[: _MAX_TOOL_RESULT_LOG_PREVIEW_CHARS - 15].rstrip()
    if preview:
        preview += "\n... truncated"
    else:
        preview = "... truncated"
    return (
        f"{prefix} captured ({len(stripped)} chars, {len(result_lines)} lines). "
        "Full output is stored in the endpoint agent workspace.\n"
        f"{preview}"
    )


def _truncate_log_message(message: str) -> str:
    if len(message) <= _MAX_AGENT_LOG_MESSAGE_CHARS:
        return message
    return message[: _MAX_AGENT_LOG_MESSAGE_CHARS - 15].rstrip() + "\n... truncated"


def _parse_report_json(value: Any) -> Optional[dict[str, Any]]:
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _load_final_report_artifact(workspace: _AgentWorkspace) -> Optional[dict[str, Any]]:
    path = workspace.work_dir / "final_report.json"
    if not path.exists():
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Endpoint agent final_report.json is not valid JSON: %s", path)
        return None
    if not isinstance(parsed, dict):
        logger.warning("Endpoint agent final_report.json is not an object: %s", path)
        return None
    return parsed


def _write_trace_record(workspace: _AgentWorkspace, data: dict[str, Any]) -> None:
    if workspace.trace_path is None:
        return
    workspace.trace_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(_redact(data, workspace.redacted_values), default=str)
    with workspace.trace_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _get_redacted_values(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value}, key=len, reverse=True))


def _get_sensitive_inherited_env_values(env: dict[str, str]) -> list[str]:
    return [env[name] for name in _INHERITED_ENV_NAMES if name != "PATH" and name in env]


def _redact(value: Any, redacted_values: Sequence[str]) -> Any:
    if isinstance(value, str):
        for redacted_value in redacted_values:
            value = value.replace(redacted_value, _REDACTION)
        return value
    if isinstance(value, dict):
        return {k: _redact(v, redacted_values) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item, redacted_values) for item in value]
    return value


def _is_debug_trace_enabled() -> bool:
    return settings.LOG_LEVEL == "DEBUG" or settings.ROOT_LOG_LEVEL == "DEBUG"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
