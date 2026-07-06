import asyncio
import enum
import json
import os
import shutil
import socket
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, Sequence
from uuid import UUID

import yaml
from pydantic import ValidationError
from sqlalchemy import func, select

from dstack._internal.core.models.config import GlobalConfig, ProjectConfig
from dstack._internal.core.models.endpoints import EndpointConfiguration
from dstack._internal.server import settings
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import (
    EndpointAgentAttemptModel,
    EndpointAgentAttemptStatus,
    EndpointModel,
    ProjectModel,
)
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
from dstack._internal.utils.common import (
    get_current_datetime,
    get_milliseconds_since_epoch,
    run_async,
)
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

_RESOURCE_DIR = Path(__file__).parent / "resources"
_ENDPOINT_PROMPT_RESOURCE_NAME = "system_prompt.md"
_AGENT_SKILL_NAMES = ["dstack", "dstack-prototyping"]
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
_AGENT_LOG_BATCH_SIZE = 1
_AGENT_PROGRESS_LOG_NAME = "progress.jsonl"
_AGENT_PROCESS_STATE_NAME = "agent_process.json"
_AGENT_STDOUT_LOG_NAME = "agent_stdout.jsonl"
_AGENT_STDERR_LOG_NAME = "agent_stderr.jsonl"
_AGENT_PROGRESS_POLL_SECONDS = 1.0
_CLAUDE_AGENT_TOOLS = "Bash,Read,Write,Edit,WebFetch,WebSearch,StructuredOutput"


@dataclass(frozen=True)
class _AgentRunnerResult:
    report: Optional[AgentFinalReport] = None
    error: Optional[str] = None


@dataclass
class _AgentProcessOutput:
    report_data: Optional[dict[str, Any]] = None
    result_error: Optional[str] = None
    spent_budget: Optional[float] = None
    stdout_tail: str = ""


class ClaudeAgentService(AgentService):
    def __init__(
        self,
        runner: Optional[
            Callable[["_AgentWorkspace", dict[str, Any]], Awaitable[_AgentRunnerResult]]
        ] = None,
        workspace_base_dir: Path = settings.SERVER_DATA_DIR_PATH / "endpoint_agent_runs",
    ) -> None:
        self._runner = runner
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
            max_agent_budget = get_effective_max_agent_budget(
                EndpointConfiguration.__response__.parse_raw(endpoint_model.configuration)
            )
            attempt = await _get_or_create_agent_attempt(
                endpoint_model=endpoint_model,
                workspace_base_dir=self._workspace_base_dir,
                max_agent_budget=max_agent_budget,
            )
            workspace = _prepare_workspace(
                endpoint_model=endpoint_model,
                workspace_root_dir=Path(attempt.workspace_path),
            )
        except Exception as e:
            logger.warning("Failed to prepare endpoint agent workspace: %s", e, exc_info=True)
            return AgentProvisioningResult(
                error=f"Failed to prepare endpoint agent workspace: {e}"
            )

        if self._runner is not None:
            return await _run_injected_agent_runner(
                attempt=attempt,
                workspace=workspace,
                runner=self._runner,
            )
        return await _reconcile_detached_agent_attempt(
            attempt=attempt,
            workspace=workspace,
        )


async def _run_injected_agent_runner(
    *,
    attempt: EndpointAgentAttemptModel,
    workspace: "_AgentWorkspace",
    runner: Callable[["_AgentWorkspace", dict[str, Any]], Awaitable[_AgentRunnerResult]],
) -> AgentProvisioningResult:
    reconcile_result = await _reconcile_agent_artifacts(attempt=attempt, workspace=workspace)
    if reconcile_result is not None:
        return reconcile_result

    runner_result = await runner(workspace, _build_agent_request(workspace))
    candidate_run_ids = _load_candidate_run_ids(workspace)
    if runner_result.error is not None:
        workspace.artifacts.record_error(runner_result.error)
        await _mark_agent_attempt_failed(attempt, runner_result.error)
        return AgentProvisioningResult(
            error=runner_result.error,
            candidate_run_ids=candidate_run_ids,
        )
    report = runner_result.report
    if report is None:
        error = "Server agent did not return a verification report"
        workspace.artifacts.record_error(error)
        await _mark_agent_attempt_failed(attempt, error)
        return AgentProvisioningResult(error=error, candidate_run_ids=candidate_run_ids)
    workspace.artifacts.record_report(report)
    await _mark_agent_attempt_from_report(attempt, report, spent_budget=None)

    logger.info(
        "Endpoint agent finished for endpoint %s: success=%s run_id=%s run_name=%s",
        workspace.endpoint_name,
        report.success,
        report.run_id,
        report.run_name,
    )
    return AgentProvisioningResult(
        run_id=report.run_id,
        run_name=report.run_name,
        candidate_run_ids=candidate_run_ids,
        final_report=report,
    )


async def _reconcile_detached_agent_attempt(
    *,
    attempt: EndpointAgentAttemptModel,
    workspace: "_AgentWorkspace",
) -> AgentProvisioningResult:
    reconcile_result = await _reconcile_agent_artifacts(attempt=attempt, workspace=workspace)
    if reconcile_result is not None:
        return reconcile_result

    running_pid = _get_running_agent_process_pid(workspace, attempt=attempt)
    if running_pid is not None:
        logger.info(
            "Endpoint agent process %s is already running for endpoint %s",
            running_pid,
            workspace.endpoint_name,
        )
        return AgentProvisioningResult(
            in_progress=True,
            candidate_run_ids=_load_candidate_run_ids(workspace),
        )

    if attempt.pid is not None:
        error = "Server agent process exited without a verification report"
        workspace.artifacts.record_error(error)
        await _mark_agent_attempt_failed(attempt, error)
        return AgentProvisioningResult(
            error=error,
            candidate_run_ids=_load_candidate_run_ids(workspace),
        )

    try:
        pid = _start_agent_subprocess_detached(workspace, _build_agent_request(workspace))
    except Exception as e:
        logger.warning("Failed to start endpoint agent process: %s", e, exc_info=True)
        error = f"Failed to start endpoint agent process: {e}"
        workspace.artifacts.record_error(error)
        await _mark_agent_attempt_failed(attempt, error)
        return AgentProvisioningResult(error=error)

    await _mark_agent_attempt_running(attempt, pid=pid, process_host=_get_process_host())
    return AgentProvisioningResult(in_progress=True)


async def _reconcile_agent_artifacts(
    *,
    attempt: EndpointAgentAttemptModel,
    workspace: "_AgentWorkspace",
) -> Optional[AgentProvisioningResult]:
    process_output = await _reconcile_agent_stream_files(attempt=attempt, workspace=workspace)
    await _reconcile_agent_progress(attempt=attempt, workspace=workspace)
    candidate_run_ids = _load_candidate_run_ids(workspace)

    report = _load_final_report(workspace)
    if report is None and process_output.report_data is not None:
        try:
            report = AgentFinalReport.parse_obj(process_output.report_data)
        except ValidationError as e:
            error = f"Server agent returned an invalid verification report: {e}"
            workspace.artifacts.record_error(error)
            await _mark_agent_attempt_failed(attempt, error)
            return AgentProvisioningResult(error=error, candidate_run_ids=candidate_run_ids)
    if report is not None:
        if (
            process_output.spent_budget is None
            and _get_running_agent_process_pid(workspace, attempt=attempt) is not None
        ):
            return AgentProvisioningResult(
                in_progress=True,
                candidate_run_ids=candidate_run_ids,
            )
        workspace.artifacts.record_report(report)
        await _mark_agent_attempt_from_report(
            attempt,
            report,
            spent_budget=process_output.spent_budget,
        )
        return AgentProvisioningResult(
            run_id=report.run_id,
            run_name=report.run_name,
            candidate_run_ids=candidate_run_ids,
            final_report=report,
        )

    error = _load_agent_error(workspace)
    if error is not None:
        await _mark_agent_attempt_failed(
            attempt,
            error,
            spent_budget=process_output.spent_budget,
        )
        return AgentProvisioningResult(error=error, candidate_run_ids=candidate_run_ids)
    if process_output.result_error is not None:
        error = "Server agent failed before returning a verification report"
        workspace.artifacts.record_error(error)
        await _mark_agent_attempt_failed(
            attempt,
            error,
            spent_budget=process_output.spent_budget,
        )
        return AgentProvisioningResult(error=error, candidate_run_ids=candidate_run_ids)
    return None


async def _get_or_create_agent_attempt(
    *,
    endpoint_model: EndpointModel,
    workspace_base_dir: Path,
    max_agent_budget: Optional[float],
) -> EndpointAgentAttemptModel:
    async with get_session_ctx() as session:
        res = await session.execute(
            select(EndpointAgentAttemptModel)
            .where(EndpointAgentAttemptModel.endpoint_id == endpoint_model.id)
            .order_by(EndpointAgentAttemptModel.attempt_num.desc())
            .limit(1)
        )
        attempt = res.scalar_one_or_none()
        if attempt is not None and attempt.created_at >= endpoint_model.created_at:
            return attempt

        max_attempt_num_res = await session.execute(
            select(func.max(EndpointAgentAttemptModel.attempt_num)).where(
                EndpointAgentAttemptModel.endpoint_id == endpoint_model.id
            )
        )
        attempt_num = (max_attempt_num_res.scalar_one_or_none() or 0) + 1
        now = get_current_datetime()
        legacy_workspace_path = workspace_base_dir / str(endpoint_model.id)
        if attempt_num == 1 and _has_agent_workspace_artifacts(legacy_workspace_path):
            workspace_path = legacy_workspace_path
        else:
            workspace_path = workspace_base_dir / str(endpoint_model.id) / str(attempt_num)
        attempt = EndpointAgentAttemptModel(
            endpoint_id=endpoint_model.id,
            attempt_num=attempt_num,
            status=EndpointAgentAttemptStatus.RUNNING,
            workspace_path=str(workspace_path),
            progress_log_offset=0,
            stdout_log_offset=0,
            stderr_log_offset=0,
            max_agent_budget=max_agent_budget,
            created_at=now,
            updated_at=now,
        )
        session.add(attempt)
        await session.commit()
        return attempt


def _has_agent_workspace_artifacts(root_dir: Path) -> bool:
    work_dir = root_dir / "workspace"
    return any(
        (work_dir / filename).exists()
        for filename in [
            "final_report.json",
            "agent_error.json",
            _AGENT_PROCESS_STATE_NAME,
            _AGENT_PROGRESS_LOG_NAME,
        ]
    )


async def _get_agent_attempt(session, attempt: EndpointAgentAttemptModel):
    return await session.get(
        EndpointAgentAttemptModel,
        {
            "endpoint_id": attempt.endpoint_id,
            "attempt_num": attempt.attempt_num,
        },
    )


async def _mark_agent_attempt_running(
    attempt: EndpointAgentAttemptModel,
    *,
    pid: int,
    process_host: str,
) -> None:
    async with get_session_ctx() as session:
        stored_attempt = await _get_agent_attempt(session, attempt)
        if stored_attempt is None:
            return
        stored_attempt.status = EndpointAgentAttemptStatus.RUNNING
        stored_attempt.pid = pid
        stored_attempt.process_host = process_host
        stored_attempt.updated_at = get_current_datetime()
        await session.commit()
        attempt.pid = pid
        attempt.process_host = process_host


async def _mark_agent_attempt_from_report(
    attempt: EndpointAgentAttemptModel,
    report: AgentFinalReport,
    *,
    spent_budget: Optional[float],
) -> None:
    if report.success:
        await _mark_agent_attempt_succeeded(attempt, spent_budget=spent_budget)
    else:
        await _mark_agent_attempt_failed(
            attempt,
            report.failure_summary or "Server agent did not verify the endpoint",
            spent_budget=spent_budget,
        )


async def _mark_agent_attempt_succeeded(
    attempt: EndpointAgentAttemptModel,
    *,
    spent_budget: Optional[float],
) -> None:
    now = get_current_datetime()
    async with get_session_ctx() as session:
        stored_attempt = await _get_agent_attempt(session, attempt)
        if stored_attempt is None:
            return
        stored_attempt.status = EndpointAgentAttemptStatus.SUCCEEDED
        stored_attempt.status_message = None
        if spent_budget is not None:
            stored_attempt.spent_agent_budget = spent_budget
        stored_attempt.finished_at = stored_attempt.finished_at or now
        stored_attempt.updated_at = now
        await session.commit()
        attempt.status = EndpointAgentAttemptStatus.SUCCEEDED
        attempt.status_message = None
        attempt.spent_agent_budget = stored_attempt.spent_agent_budget
        attempt.finished_at = stored_attempt.finished_at


async def _mark_agent_attempt_failed(
    attempt: EndpointAgentAttemptModel,
    error: str,
    *,
    spent_budget: Optional[float] = None,
) -> None:
    now = get_current_datetime()
    async with get_session_ctx() as session:
        stored_attempt = await _get_agent_attempt(session, attempt)
        if stored_attempt is None:
            return
        stored_attempt.status = EndpointAgentAttemptStatus.FAILED
        stored_attempt.status_message = error
        if spent_budget is not None:
            stored_attempt.spent_agent_budget = spent_budget
        stored_attempt.finished_at = stored_attempt.finished_at or now
        stored_attempt.updated_at = now
        await session.commit()
        attempt.status = EndpointAgentAttemptStatus.FAILED
        attempt.status_message = error
        attempt.spent_agent_budget = stored_attempt.spent_agent_budget
        attempt.finished_at = stored_attempt.finished_at


async def _update_agent_attempt_offsets(
    attempt: EndpointAgentAttemptModel,
    *,
    progress_log_offset: Optional[int] = None,
    stdout_log_offset: Optional[int] = None,
    stderr_log_offset: Optional[int] = None,
    spent_budget: Optional[float] = None,
) -> None:
    async with get_session_ctx() as session:
        stored_attempt = await _get_agent_attempt(session, attempt)
        if stored_attempt is None:
            return
        if progress_log_offset is not None:
            stored_attempt.progress_log_offset = progress_log_offset
            attempt.progress_log_offset = progress_log_offset
        if stdout_log_offset is not None:
            stored_attempt.stdout_log_offset = stdout_log_offset
            attempt.stdout_log_offset = stdout_log_offset
        if stderr_log_offset is not None:
            stored_attempt.stderr_log_offset = stderr_log_offset
            attempt.stderr_log_offset = stderr_log_offset
        if spent_budget is not None:
            stored_attempt.spent_agent_budget = spent_budget
            attempt.spent_agent_budget = spent_budget
        stored_attempt.updated_at = get_current_datetime()
        await session.commit()


async def _reconcile_agent_progress(
    *,
    attempt: EndpointAgentAttemptModel,
    workspace: "_AgentWorkspace",
) -> None:
    offset = await _flush_agent_progress_logs(
        workspace,
        offset=attempt.progress_log_offset,
        include_partial=False,
    )
    if offset != attempt.progress_log_offset:
        await _update_agent_attempt_offsets(attempt, progress_log_offset=offset)


async def _reconcile_agent_stream_files(
    *,
    attempt: EndpointAgentAttemptModel,
    workspace: "_AgentWorkspace",
) -> _AgentProcessOutput:
    stdout_output, stdout_offset = await _read_agent_stream_file(
        workspace=workspace,
        path=workspace.work_dir / _AGENT_STDOUT_LOG_NAME,
        offset=attempt.stdout_log_offset,
        stream_name="stdout",
    )
    stderr_output, stderr_offset = await _read_agent_stream_file(
        workspace=workspace,
        path=workspace.work_dir / _AGENT_STDERR_LOG_NAME,
        offset=attempt.stderr_log_offset,
        stream_name="stderr",
    )
    output = _merge_process_outputs(stdout_output, stderr_output)
    if (
        stdout_offset != attempt.stdout_log_offset
        or stderr_offset != attempt.stderr_log_offset
        or output.spent_budget is not None
    ):
        await _update_agent_attempt_offsets(
            attempt,
            stdout_log_offset=stdout_offset,
            stderr_log_offset=stderr_offset,
            spent_budget=output.spent_budget,
        )
    return output


def _load_candidate_run_ids(workspace: "_AgentWorkspace") -> tuple[UUID, ...]:
    path = workspace.work_dir / "candidates.jsonl"
    if not path.exists():
        return ()
    run_ids: list[UUID] = []
    seen: set[UUID] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            _write_trace_record(
                workspace,
                {"type": "agent-candidate-invalid", "line": line},
            )
            continue
        if not isinstance(parsed, dict):
            continue
        raw_run_id = parsed.get("run_id")
        if not isinstance(raw_run_id, str) or not raw_run_id.strip():
            continue
        try:
            run_id = UUID(raw_run_id)
        except ValueError:
            _write_trace_record(
                workspace,
                {"type": "agent-candidate-invalid-run-id", "run_id": raw_run_id},
            )
            continue
        if run_id not in seen:
            seen.add(run_id)
            run_ids.append(run_id)
    return tuple(run_ids)


def _load_agent_error(workspace: "_AgentWorkspace") -> Optional[str]:
    path = workspace.work_dir / "agent_error.json"
    if not path.exists():
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "Server agent failed"
    if not isinstance(parsed, dict):
        return "Server agent failed"
    failure_summary = parsed.get("failure_summary")
    if isinstance(failure_summary, str) and failure_summary.strip():
        return failure_summary
    return "Server agent failed"


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

    @property
    def progress_path(self) -> Path:
        return self.work_dir / _AGENT_PROGRESS_LOG_NAME


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
    workspace_root_dir: Path,
) -> _AgentWorkspace:
    configuration = EndpointConfiguration.__response__.parse_raw(endpoint_model.configuration)

    root_dir = workspace_root_dir
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
    _install_agent_skills(workspace)
    workspace.artifacts.initialize()
    return workspace


class _AgentArtifactRecorder:
    def __init__(self, workspace: _AgentWorkspace) -> None:
        self._workspace = workspace
        self._command_counter = 0

    def initialize(self) -> None:
        self._workspace.work_dir.mkdir(parents=True, exist_ok=True)
        self._command_counter = self._get_last_command_output_num()
        self._update_agent_state(phase="starting")
        for filename in [
            "sources.jsonl",
            "candidates.jsonl",
            "commands.jsonl",
            _AGENT_PROGRESS_LOG_NAME,
        ]:
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

    def _get_last_command_output_num(self) -> int:
        output_dir = self._workspace.work_dir / "command-output"
        if not output_dir.exists():
            return 0
        nums = []
        for path in output_dir.glob("*.txt"):
            try:
                nums.append(int(path.stem))
            except ValueError:
                continue
        return max(nums, default=0)


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
    return f"""{_load_endpoint_prompt()}

Deploy endpoint {workspace.endpoint_name!r} for model {workspace.model!r}.

{workspace.endpoint_constraints}

Bundled Claude Code skills are installed in `.claude/skills`. Load and follow:
- `/dstack`
- `/dstack-prototyping`

Required final service:
- service YAML type: service
- service YAML must set `model: {workspace.model}`
- service run name must not equal the endpoint name `{workspace.endpoint_name}`
- for sequential service attempts, prefer `{workspace.endpoint_name}-1`, `{workspace.endpoint_name}-2`, etc.
- submit runs detached with `dstack apply -f <file> -y -d`
- use concise, unique run names that are useful for debugging
- the successful final report must include the verified service run `run_id`

When you have a terminal result, write `final_report.json` in the workspace with the
same fields requested by the JSON schema, then return only the structured final report.
"""


def _load_endpoint_prompt() -> str:
    return (_RESOURCE_DIR / _ENDPOINT_PROMPT_RESOURCE_NAME).read_text(encoding="utf-8").strip()


def _install_agent_skills(workspace: _AgentWorkspace) -> None:
    source_dir = _get_packaged_skills_dir()
    target_dir = workspace.work_dir / ".claude" / "skills"
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    for skill_name in _AGENT_SKILL_NAMES:
        source = source_dir / skill_name
        if not (source / "SKILL.md").is_file():
            raise FileNotFoundError(f"Missing endpoint agent skill: {skill_name}")
        shutil.copytree(source, target_dir / skill_name)


def _get_packaged_skills_dir() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "skills"
        if (candidate / "dstack" / "SKILL.md").is_file():
            return candidate
    raise FileNotFoundError("Could not find packaged dstack skills")


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
    if isinstance(value, enum.Enum):
        return str(value.value)
    if hasattr(value, "name") and getattr(value, "project", None) is None:
        return str(value.name)
    if hasattr(value, "json"):
        return json.dumps(json.loads(value.json()), sort_keys=True)
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _start_agent_subprocess_detached(
    workspace: _AgentWorkspace,
    request: dict[str, Any],
) -> int:
    cmd = _build_claude_command(request)
    workspace.artifacts.mark_running()
    stdout_path = workspace.work_dir / _AGENT_STDOUT_LOG_NAME
    stderr_path = workspace.work_dir / _AGENT_STDERR_LOG_NAME
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    with (
        stdout_path.open("ab") as stdout,
        stderr_path.open("ab") as stderr,
    ):
        proc = subprocess.Popen(
            cmd,
            cwd=workspace.work_dir,
            env=request["env"],
            stdout=stdout,
            stderr=stderr,
            close_fds=True,
            start_new_session=True,
        )
    _write_agent_process_state(workspace, proc.pid)
    _write_trace_record(
        workspace,
        {
            "type": "agent-process-started",
            "pid": proc.pid,
            "host": _get_process_host(),
        },
    )
    return proc.pid


async def _run_agent_in_subprocess(
    workspace: _AgentWorkspace,
    request: dict[str, Any],
) -> _AgentRunnerResult:
    cmd = _build_claude_command(request)
    workspace.artifacts.mark_running()
    progress_tailer = _AgentProgressLogTailer(workspace)
    progress_task = asyncio.create_task(progress_tailer.run())
    proc: asyncio.subprocess.Process | None = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=workspace.work_dir,
            env=request["env"],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _write_agent_process_state(workspace, proc.pid)
        assert proc.stdout is not None
        assert proc.stderr is not None
        stdout_task = asyncio.create_task(_read_agent_stdout(proc.stdout, workspace))
        stderr_task = asyncio.create_task(_read_agent_stderr(proc.stderr, workspace))
        stdout_output, stderr_output, returncode = await asyncio.gather(
            stdout_task,
            stderr_task,
            proc.wait(),
        )
    finally:
        progress_task.cancel()
        with suppress(asyncio.CancelledError):
            await progress_task
        await progress_tailer.flush(include_partial=True)
        if proc is not None and proc.returncode is not None:
            _clear_agent_process_state(workspace, proc.pid)
    process_output = _merge_process_outputs(stdout_output, stderr_output)
    _write_trace_record(
        workspace,
        {
            "type": "agent-process",
            "returncode": returncode,
        },
    )
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
        _process_agent_stream_line(
            line=line,
            workspace=workspace,
            stream_name=stream_name,
            output=output,
        )


async def _read_agent_stream_file(
    *,
    workspace: _AgentWorkspace,
    path: Path,
    offset: int,
    stream_name: str,
) -> tuple[_AgentProcessOutput, int]:
    output = _AgentProcessOutput()
    lines, new_offset = _read_complete_file_lines(path=path, offset=offset)
    for line in lines:
        _process_agent_stream_line(
            line=line,
            workspace=workspace,
            stream_name=stream_name,
            output=output,
        )
    return output, new_offset


def _process_agent_stream_line(
    *,
    line: str,
    workspace: _AgentWorkspace,
    stream_name: str,
    output: _AgentProcessOutput,
) -> None:
    output.stdout_tail = _append_bounded_output(output.stdout_tail, line)
    if not line.strip():
        return
    try:
        message = json.loads(line)
    except json.JSONDecodeError:
        message = {"type": "raw-output", "stream": stream_name, "line": line.rstrip("\r\n")}
        _write_trace_record(workspace, message)
        return
    if stream_name != "stdout":
        message.setdefault("stream", stream_name)
    _write_trace_record(workspace, message)
    workspace.artifacts.record_stream_message(message)
    _update_agent_process_output(output, message)


def _read_complete_file_lines(*, path: Path, offset: int) -> tuple[list[str], int]:
    if not path.exists():
        return [], offset
    size = path.stat().st_size
    if size < offset:
        offset = 0
    with path.open("rb") as f:
        f.seek(offset)
        data = f.read()
    if not data:
        return [], offset
    newline_pos = max(data.rfind(b"\n"), data.rfind(b"\r"))
    if newline_pos == -1:
        return [], offset
    complete = data[: newline_pos + 1]
    new_offset = offset + len(complete)
    lines = [line.decode(errors="replace") for line in complete.splitlines(keepends=True)]
    return lines, new_offset


class _AgentProgressLogTailer:
    def __init__(self, workspace: _AgentWorkspace) -> None:
        self._workspace = workspace
        self._offset = (
            workspace.progress_path.stat().st_size if workspace.progress_path.exists() else 0
        )
        self._partial = ""

    async def run(self) -> None:
        while True:
            await self.flush()
            await asyncio.sleep(_AGENT_PROGRESS_POLL_SECONDS)

    async def flush(self, *, include_partial: bool = False) -> None:
        path = self._workspace.progress_path
        if not path.exists():
            return
        if path.stat().st_size < self._offset:
            self._offset = 0
            self._partial = ""
        with path.open("r", encoding="utf-8", errors="replace") as f:
            f.seek(self._offset)
            text = f.read()
            self._offset = f.tell()
        if not text and not (include_partial and self._partial):
            return
        self._partial += text
        lines = self._partial.splitlines(keepends=True)
        self._partial = ""
        for line in lines:
            if not include_partial and not line.endswith(("\n", "\r")):
                self._partial = line
                continue
            await self._write_progress_line(line.rstrip("\r\n"))

    async def _write_progress_line(self, line: str) -> None:
        if not line.strip():
            return
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            _write_trace_record(
                self._workspace,
                {"type": "agent-progress-invalid", "line": line},
            )
            return
        message = _format_agent_progress_log_message(parsed)
        if message is None:
            _write_trace_record(
                self._workspace,
                {"type": "agent-progress-ignored", "record": parsed},
            )
            return
        await _write_agent_log(self._workspace, message)


async def _flush_agent_progress_logs(
    workspace: _AgentWorkspace,
    *,
    offset: int,
    include_partial: bool,
) -> int:
    path = workspace.progress_path
    lines, new_offset = _read_complete_file_lines(path=path, offset=offset)
    if include_partial and path.exists():
        size = path.stat().st_size
        if size > new_offset:
            with path.open("rb") as f:
                f.seek(new_offset)
                data = f.read()
            if data:
                lines.append(data.decode(errors="replace"))
                new_offset = size
    for line in lines:
        await _write_agent_progress_line(workspace, line.rstrip("\r\n"))
    await _flush_agent_logs(workspace)
    return new_offset


async def _write_agent_progress_line(workspace: _AgentWorkspace, line: str) -> None:
    if not line.strip():
        return
    try:
        parsed = json.loads(line)
    except json.JSONDecodeError:
        _write_trace_record(
            workspace,
            {"type": "agent-progress-invalid", "line": line},
        )
        return
    message = _format_agent_progress_log_message(parsed)
    if message is None:
        _write_trace_record(
            workspace,
            {"type": "agent-progress-ignored", "record": parsed},
        )
        return
    await _write_agent_log(workspace, message)


def _format_agent_progress_log_message(record: Any) -> Optional[str]:
    if not isinstance(record, dict):
        return None
    message = record.get("message")
    if not isinstance(message, str) or not message.strip():
        return None
    phase = record.get("phase")
    if isinstance(phase, str) and phase.strip():
        return f"{phase.strip()}: {message.strip()}"
    return message.strip()


def _update_agent_process_output(
    output: _AgentProcessOutput,
    message: dict[str, Any],
) -> None:
    if message.get("type") != "result":
        return
    total_cost = message.get("total_cost_usd")
    if isinstance(total_cost, (int, float)):
        output.spent_budget = float(total_cost)
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
        if output.spent_budget is not None:
            merged.spent_budget = output.spent_budget
        merged.stdout_tail = _append_bounded_output(merged.stdout_tail, output.stdout_tail)
    return merged


async def _write_agent_log(workspace: _AgentWorkspace, message: str) -> None:
    if workspace.log_writer is None:
        return
    message = _redact(message, workspace.redacted_values)
    await workspace.log_writer.write(message)


async def _flush_agent_logs(workspace: _AgentWorkspace) -> None:
    if workspace.log_writer is None:
        return
    await workspace.log_writer.flush()


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


def _load_final_report(workspace: _AgentWorkspace) -> Optional[AgentFinalReport]:
    report_data = _load_final_report_artifact(workspace)
    if report_data is None:
        return None
    try:
        return AgentFinalReport.parse_obj(report_data)
    except ValidationError:
        logger.warning(
            "Endpoint agent final_report.json does not match the report schema: %s",
            workspace.work_dir / "final_report.json",
            exc_info=True,
        )
        return None


def _write_agent_process_state(workspace: _AgentWorkspace, pid: int) -> None:
    path = workspace.work_dir / _AGENT_PROCESS_STATE_NAME
    data = {
        "pid": pid,
        "host": _get_process_host(),
        "started_at": _utcnow_iso(),
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _clear_agent_process_state(workspace: _AgentWorkspace, pid: int) -> None:
    path = workspace.work_dir / _AGENT_PROCESS_STATE_NAME
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        path.unlink(missing_ok=True)
        return
    if data.get("pid") == pid:
        path.unlink(missing_ok=True)


def _get_running_agent_process_pid(
    workspace: _AgentWorkspace,
    attempt: Optional[EndpointAgentAttemptModel] = None,
) -> Optional[int]:
    if attempt is not None and attempt.process_host not in (None, _get_process_host()):
        return attempt.pid
    path = workspace.work_dir / _AGENT_PROCESS_STATE_NAME
    if not path.exists():
        if attempt is None or attempt.pid is None:
            return None
        if attempt.process_host not in (None, _get_process_host()):
            return attempt.pid
        return attempt.pid if _is_process_running(attempt.pid) else None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        path.unlink(missing_ok=True)
        return None
    host = data.get("host")
    if isinstance(host, str) and host and host != _get_process_host():
        pid = data.get("pid")
        return pid if isinstance(pid, int) else None
    pid = data.get("pid")
    if not isinstance(pid, int):
        path.unlink(missing_ok=True)
        return None
    if _is_process_running(pid):
        return pid
    path.unlink(missing_ok=True)
    return None


def _get_process_host() -> str:
    return socket.gethostname()


def _is_process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


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
