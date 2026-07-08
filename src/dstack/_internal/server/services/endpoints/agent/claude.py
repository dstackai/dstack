import asyncio
import enum
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, Sequence
from uuid import UUID

import yaml
from pydantic import ValidationError
from sqlalchemy import exists, func, or_, select

from dstack._internal.core.models.config import GlobalConfig, ProjectConfig
from dstack._internal.core.models.endpoints import EndpointConfiguration
from dstack._internal.core.models.fleets import FleetStatus
from dstack._internal.server import settings
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import (
    EndpointAgentSessionModel,
    EndpointAgentSessionStatus,
    EndpointModel,
    ExportedFleetModel,
    FleetModel,
    ImportModel,
    ProjectModel,
)
from dstack._internal.server.schemas.runner import LogEvent
from dstack._internal.server.services import logs as logs_services
from dstack._internal.server.services.endpoints.agent import (
    AgentPlan,
    AgentProvisioningResult,
    AgentService,
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
_AGENT_SUBMISSIONS_LOG_NAME = "submissions.jsonl"
_AGENT_PROCESS_STATE_NAME = "agent_process.json"
_AGENT_STDOUT_LOG_NAME = "agent_stdout.jsonl"
_AGENT_STDERR_LOG_NAME = "agent_stderr.jsonl"
_AGENT_PROGRESS_POLL_SECONDS = 1.0
_AGENT_PROCESS_ABORT_GRACE_SECONDS = 1.0
_CLAUDE_AGENT_TOOLS = "Bash,Read,Write,Edit,WebFetch,WebSearch,StructuredOutput"
_CLAUDE_EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
_AGENT_ABORT_MESSAGE = "Endpoint stop requested"
_AGENT_BIN_DIR_NAME = "bin"
_AGENT_PROGRESS_ENV = "DSTACK_ENDPOINT_PROGRESS_LOG"
_ENDPOINT_NO_FLEETS_MESSAGE = (
    "The project has no fleets. Create one before submitting an endpoint."
)
_ENDPOINT_NO_MATCHING_FLEETS_MESSAGE = (
    "No fleets match the endpoint configuration. Create a fleet or update `fleets` before "
    "submitting an endpoint."
)
_AGENT_START_PROGRESS_TEMPLATE = (
    "Starting endpoint prototyping agent for {model}. Allowed fleets: {fleets}. "
    "The agent will inspect offers, choose a service recipe, deploy it, and verify "
    "the model API before the endpoint becomes active."
)


@dataclass(frozen=True)
class _AgentRunnerResult:
    report: Optional[AgentFinalReport] = None
    error: Optional[str] = None


@dataclass
class _AgentProcessOutput:
    report_data: Optional[dict[str, Any]] = None
    result_error: Optional[str] = None
    stdout_tail: str = ""


@dataclass(frozen=True)
class _AgentProcessState:
    pid: int
    pgid: int
    host: Optional[str]


@dataclass(frozen=True)
class _EndpointAgentConstraints:
    prompt_text: str
    allowed_fleets: tuple[str, ...]


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
            configuration = EndpointConfiguration.__response__.parse_raw(
                endpoint_model.configuration
            )
            agent_constraints = await _get_endpoint_agent_constraints(
                endpoint_model=endpoint_model,
                configuration=configuration,
            )
            if not agent_constraints.allowed_fleets:
                return AgentProvisioningResult(
                    error=_get_endpoint_no_fleets_message(configuration)
                )
            agent_session = await _get_or_create_agent_session(
                endpoint_model=endpoint_model,
                workspace_base_dir=self._workspace_base_dir,
            )
            workspace = _prepare_workspace(
                endpoint_model=endpoint_model,
                workspace_root_dir=Path(agent_session.workspace_path),
                agent_constraints=agent_constraints,
            )
        except Exception as e:
            logger.warning("Failed to prepare endpoint agent workspace: %s", e, exc_info=True)
            return AgentProvisioningResult(
                error=f"Failed to prepare endpoint agent workspace: {e}"
            )

        if self._runner is not None:
            return await _run_injected_agent_runner(
                agent_session=agent_session,
                workspace=workspace,
                runner=self._runner,
            )
        return await _reconcile_detached_agent_session(
            agent_session=agent_session,
            workspace=workspace,
        )

    async def abort_endpoint(self, endpoint_model: EndpointModel) -> bool:
        agent_session = await _get_latest_agent_session(endpoint_model)
        if agent_session is None or agent_session.status != EndpointAgentSessionStatus.RUNNING:
            return True
        try:
            workspace = _prepare_workspace(
                endpoint_model=endpoint_model,
                workspace_root_dir=Path(agent_session.workspace_path),
                install_skills=False,
            )
        except Exception:
            logger.warning(
                "Failed to prepare endpoint agent workspace for abort: endpoint=%s",
                endpoint_model.name,
                exc_info=True,
            )
            return False

        aborted = await _abort_agent_session_process(
            agent_session=agent_session,
            workspace=workspace,
        )
        if not aborted:
            return False
        workspace.artifacts.record_error(_AGENT_ABORT_MESSAGE)
        await _mark_agent_session_failed(agent_session, _AGENT_ABORT_MESSAGE)
        await _flush_agent_logs(workspace)
        return True


async def _run_injected_agent_runner(
    *,
    agent_session: EndpointAgentSessionModel,
    workspace: "_AgentWorkspace",
    runner: Callable[["_AgentWorkspace", dict[str, Any]], Awaitable[_AgentRunnerResult]],
) -> AgentProvisioningResult:
    reconcile_result = await _reconcile_agent_artifacts(
        agent_session=agent_session,
        workspace=workspace,
    )
    if reconcile_result is not None:
        return reconcile_result

    runner_result = await runner(workspace, _build_agent_request(workspace))
    submissions = _load_submissions(workspace)
    if runner_result.error is not None:
        workspace.artifacts.record_error(runner_result.error)
        await _mark_agent_session_failed(agent_session, runner_result.error)
        return AgentProvisioningResult(
            error=runner_result.error,
            submitted_run_ids=submissions.run_ids,
            submitted_run_names=submissions.run_names,
        )
    report = runner_result.report
    if report is None:
        error = "Server agent did not return a final report"
        workspace.artifacts.record_error(error)
        await _mark_agent_session_failed(agent_session, error)
        return AgentProvisioningResult(
            error=error,
            submitted_run_ids=submissions.run_ids,
            submitted_run_names=submissions.run_names,
        )
    workspace.artifacts.record_report(report)
    await _mark_agent_session_from_report(agent_session, report)

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
        submitted_run_ids=submissions.run_ids,
        submitted_run_names=submissions.run_names,
        final_report=report,
    )


async def _reconcile_detached_agent_session(
    *,
    agent_session: EndpointAgentSessionModel,
    workspace: "_AgentWorkspace",
) -> AgentProvisioningResult:
    reconcile_result = await _reconcile_agent_artifacts(
        agent_session=agent_session,
        workspace=workspace,
    )
    if reconcile_result is not None:
        return reconcile_result

    running_pid = _get_running_agent_process_pid(workspace, agent_session=agent_session)
    if running_pid is not None:
        logger.info(
            "Endpoint agent process %s is already running for endpoint %s",
            running_pid,
            workspace.endpoint_name,
        )
        submissions = _load_submissions(workspace)
        return AgentProvisioningResult(
            in_progress=True,
            submitted_run_ids=submissions.run_ids,
            submitted_run_names=submissions.run_names,
        )

    if agent_session.pid is not None:
        logger.info(
            "Endpoint agent process %s is no longer running for endpoint %s; "
            "resuming session %s from workspace",
            agent_session.pid,
            workspace.endpoint_name,
            agent_session.session_num,
        )
        _write_trace_record(
            workspace,
            {
                "type": "agent-process-resume",
                "pid": agent_session.pid,
                "process_host": agent_session.process_host,
                "session_num": agent_session.session_num,
            },
        )
        await _write_agent_session_progress(
            agent_session,
            workspace,
            "Resuming endpoint prototyping agent from the existing workspace.",
        )
        await _clear_agent_session_process(agent_session)

    try:
        await _write_agent_session_progress(
            agent_session,
            workspace,
            _get_agent_start_progress_message(workspace),
        )
        pid = _start_agent_subprocess_detached(workspace, _build_agent_request(workspace))
    except Exception as e:
        logger.warning("Failed to start endpoint agent process: %s", e, exc_info=True)
        error = f"Failed to start endpoint agent process: {e}"
        workspace.artifacts.record_error(error)
        await _mark_agent_session_failed(agent_session, error)
        return AgentProvisioningResult(error=error)

    await _mark_agent_session_running(agent_session, pid=pid, process_host=_get_process_host())
    return AgentProvisioningResult(in_progress=True)


async def _reconcile_agent_artifacts(
    *,
    agent_session: EndpointAgentSessionModel,
    workspace: "_AgentWorkspace",
) -> Optional[AgentProvisioningResult]:
    process_output = await _reconcile_agent_stream_files(
        agent_session=agent_session,
        workspace=workspace,
    )
    await _reconcile_agent_progress(agent_session=agent_session, workspace=workspace)
    submissions = _load_submissions(workspace)

    report = _load_final_report(workspace)
    if report is None and process_output.report_data is not None:
        try:
            report = AgentFinalReport.parse_obj(process_output.report_data)
        except ValidationError as e:
            error = f"Server agent returned an invalid final report: {e}"
            workspace.artifacts.record_error(error)
            await _mark_agent_session_failed(agent_session, error)
            return AgentProvisioningResult(
                error=error,
                submitted_run_ids=submissions.run_ids,
                submitted_run_names=submissions.run_names,
            )
    if report is not None:
        if _get_running_agent_process_pid(workspace, agent_session=agent_session) is not None:
            return AgentProvisioningResult(
                in_progress=True,
                submitted_run_ids=submissions.run_ids,
                submitted_run_names=submissions.run_names,
            )
        workspace.artifacts.record_report(report)
        await _mark_agent_session_from_report(agent_session, report)
        return AgentProvisioningResult(
            run_id=report.run_id,
            run_name=report.run_name,
            submitted_run_ids=submissions.run_ids,
            submitted_run_names=submissions.run_names,
            final_report=report,
        )

    error = _load_agent_error(workspace)
    if error is not None:
        await _mark_agent_session_failed(agent_session, error)
        return AgentProvisioningResult(
            error=error,
            submitted_run_ids=submissions.run_ids,
            submitted_run_names=submissions.run_names,
        )
    if process_output.result_error is not None:
        error = "Server agent failed before returning a final report"
        workspace.artifacts.record_error(error)
        await _mark_agent_session_failed(agent_session, error)
        return AgentProvisioningResult(
            error=error,
            submitted_run_ids=submissions.run_ids,
            submitted_run_names=submissions.run_names,
        )
    return None


async def _get_or_create_agent_session(
    *,
    endpoint_model: EndpointModel,
    workspace_base_dir: Path,
) -> EndpointAgentSessionModel:
    async with get_session_ctx() as db_session:
        res = await db_session.execute(
            select(EndpointAgentSessionModel)
            .where(EndpointAgentSessionModel.endpoint_id == endpoint_model.id)
            .order_by(EndpointAgentSessionModel.session_num.desc())
            .limit(1)
        )
        agent_session = res.scalar_one_or_none()
        if agent_session is not None and agent_session.created_at >= endpoint_model.created_at:
            return agent_session

        max_session_num_res = await db_session.execute(
            select(func.max(EndpointAgentSessionModel.session_num)).where(
                EndpointAgentSessionModel.endpoint_id == endpoint_model.id
            )
        )
        session_num = (max_session_num_res.scalar_one_or_none() or 0) + 1
        now = get_current_datetime()
        legacy_workspace_path = workspace_base_dir / str(endpoint_model.id)
        if session_num == 1 and _has_agent_workspace_artifacts(legacy_workspace_path):
            workspace_path = legacy_workspace_path
        else:
            workspace_path = workspace_base_dir / str(endpoint_model.id) / str(session_num)
        agent_session = EndpointAgentSessionModel(
            endpoint_id=endpoint_model.id,
            session_num=session_num,
            status=EndpointAgentSessionStatus.RUNNING,
            workspace_path=str(workspace_path),
            progress_log_offset=0,
            stdout_log_offset=0,
            stderr_log_offset=0,
            created_at=now,
            updated_at=now,
        )
        db_session.add(agent_session)
        await db_session.commit()
        return agent_session


async def _get_latest_agent_session(
    endpoint_model: EndpointModel,
) -> Optional[EndpointAgentSessionModel]:
    async with get_session_ctx() as db_session:
        res = await db_session.execute(
            select(EndpointAgentSessionModel)
            .where(EndpointAgentSessionModel.endpoint_id == endpoint_model.id)
            .order_by(EndpointAgentSessionModel.session_num.desc())
            .limit(1)
        )
        return res.scalar_one_or_none()


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


async def _get_agent_session(db_session, agent_session: EndpointAgentSessionModel):
    return await db_session.get(
        EndpointAgentSessionModel,
        {
            "endpoint_id": agent_session.endpoint_id,
            "session_num": agent_session.session_num,
        },
    )


async def _mark_agent_session_running(
    agent_session: EndpointAgentSessionModel,
    *,
    pid: int,
    process_host: str,
) -> None:
    async with get_session_ctx() as db_session:
        stored_session = await _get_agent_session(db_session, agent_session)
        if stored_session is None:
            return
        stored_session.status = EndpointAgentSessionStatus.RUNNING
        stored_session.pid = pid
        stored_session.process_host = process_host
        stored_session.updated_at = get_current_datetime()
        await db_session.commit()
        agent_session.pid = pid
        agent_session.process_host = process_host


async def _clear_agent_session_process(agent_session: EndpointAgentSessionModel) -> None:
    async with get_session_ctx() as db_session:
        stored_session = await _get_agent_session(db_session, agent_session)
        if stored_session is None:
            return
        stored_session.pid = None
        stored_session.process_host = None
        stored_session.updated_at = get_current_datetime()
        await db_session.commit()
        agent_session.pid = None
        agent_session.process_host = None


async def _mark_agent_session_from_report(
    agent_session: EndpointAgentSessionModel,
    report: AgentFinalReport,
) -> None:
    if report.success:
        await _mark_agent_session_succeeded(agent_session)
    else:
        await _mark_agent_session_failed(
            agent_session,
            report.failure_summary or "Server agent did not verify the endpoint",
        )


async def _mark_agent_session_succeeded(
    agent_session: EndpointAgentSessionModel,
) -> None:
    now = get_current_datetime()
    async with get_session_ctx() as db_session:
        stored_session = await _get_agent_session(db_session, agent_session)
        if stored_session is None:
            return
        stored_session.status = EndpointAgentSessionStatus.SUCCEEDED
        stored_session.status_message = None
        stored_session.finished_at = stored_session.finished_at or now
        stored_session.updated_at = now
        await db_session.commit()
        agent_session.status = EndpointAgentSessionStatus.SUCCEEDED
        agent_session.status_message = None
        agent_session.finished_at = stored_session.finished_at


async def _mark_agent_session_failed(
    agent_session: EndpointAgentSessionModel,
    error: str,
) -> None:
    now = get_current_datetime()
    async with get_session_ctx() as db_session:
        stored_session = await _get_agent_session(db_session, agent_session)
        if stored_session is None:
            return
        stored_session.status = EndpointAgentSessionStatus.FAILED
        stored_session.status_message = error
        stored_session.finished_at = stored_session.finished_at or now
        stored_session.updated_at = now
        await db_session.commit()
        agent_session.status = EndpointAgentSessionStatus.FAILED
        agent_session.status_message = error
        agent_session.finished_at = stored_session.finished_at


async def _update_agent_session_offsets(
    agent_session: EndpointAgentSessionModel,
    *,
    progress_log_offset: Optional[int] = None,
    stdout_log_offset: Optional[int] = None,
    stderr_log_offset: Optional[int] = None,
) -> None:
    async with get_session_ctx() as db_session:
        stored_session = await _get_agent_session(db_session, agent_session)
        if stored_session is None:
            return
        if progress_log_offset is not None:
            stored_session.progress_log_offset = progress_log_offset
            agent_session.progress_log_offset = progress_log_offset
        if stdout_log_offset is not None:
            stored_session.stdout_log_offset = stdout_log_offset
            agent_session.stdout_log_offset = stdout_log_offset
        if stderr_log_offset is not None:
            stored_session.stderr_log_offset = stderr_log_offset
            agent_session.stderr_log_offset = stderr_log_offset
        stored_session.updated_at = get_current_datetime()
        await db_session.commit()


async def _reconcile_agent_progress(
    *,
    agent_session: EndpointAgentSessionModel,
    workspace: "_AgentWorkspace",
) -> None:
    offset = await _flush_agent_progress_logs(
        workspace,
        offset=agent_session.progress_log_offset,
        include_partial=False,
    )
    if offset != agent_session.progress_log_offset:
        await _update_agent_session_offsets(agent_session, progress_log_offset=offset)


async def _write_agent_session_progress(
    agent_session: EndpointAgentSessionModel,
    workspace: "_AgentWorkspace",
    message: str,
) -> None:
    _append_agent_progress_record(workspace, message)
    offset = workspace.progress_path.stat().st_size
    await _write_agent_log(workspace, message)
    await _flush_agent_logs(workspace)
    await _update_agent_session_offsets(agent_session, progress_log_offset=offset)


def _append_agent_progress_record(workspace: "_AgentWorkspace", message: str) -> None:
    workspace.progress_path.parent.mkdir(parents=True, exist_ok=True)
    with workspace.progress_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"message": message}, ensure_ascii=True) + "\n")


def _get_agent_start_progress_message(workspace: "_AgentWorkspace") -> str:
    fleets = ", ".join(workspace.allowed_fleets) if workspace.allowed_fleets else "none"
    return _AGENT_START_PROGRESS_TEMPLATE.format(model=workspace.model, fleets=fleets)


async def _reconcile_agent_stream_files(
    *,
    agent_session: EndpointAgentSessionModel,
    workspace: "_AgentWorkspace",
) -> _AgentProcessOutput:
    stdout_output, stdout_offset = await _read_agent_stream_file(
        workspace=workspace,
        path=workspace.work_dir / _AGENT_STDOUT_LOG_NAME,
        offset=agent_session.stdout_log_offset,
        stream_name="stdout",
    )
    stderr_output, stderr_offset = await _read_agent_stream_file(
        workspace=workspace,
        path=workspace.work_dir / _AGENT_STDERR_LOG_NAME,
        offset=agent_session.stderr_log_offset,
        stream_name="stderr",
    )
    output = _merge_process_outputs(stdout_output, stderr_output)
    if (
        stdout_offset != agent_session.stdout_log_offset
        or stderr_offset != agent_session.stderr_log_offset
    ):
        await _update_agent_session_offsets(
            agent_session,
            stdout_log_offset=stdout_offset,
            stderr_log_offset=stderr_offset,
        )
    return output


@dataclass(frozen=True)
class _AgentSubmissions:
    run_ids: tuple[UUID, ...] = ()
    run_names: tuple[str, ...] = ()


def _load_submissions(workspace: "_AgentWorkspace") -> _AgentSubmissions:
    path = workspace.work_dir / _AGENT_SUBMISSIONS_LOG_NAME
    if not path.exists():
        return _AgentSubmissions()
    run_ids: list[UUID] = []
    run_names: list[str] = []
    seen_run_ids: set[UUID] = set()
    seen_run_names: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            _write_trace_record(
                workspace,
                {"type": "agent-submission-invalid", "path": str(path), "line": line},
            )
            continue
        if not isinstance(parsed, dict):
            continue
        raw_name = parsed.get("name")
        if isinstance(raw_name, str):
            run_name = raw_name.strip()
            if run_name and run_name not in seen_run_names:
                seen_run_names.add(run_name)
                run_names.append(run_name)
        raw_run_id = parsed.get("run_id")
        if not isinstance(raw_run_id, str) or not raw_run_id.strip():
            continue
        try:
            run_id = UUID(raw_run_id)
        except ValueError:
            _write_trace_record(
                workspace,
                {
                    "type": "agent-submission-invalid-run-id",
                    "path": str(path),
                    "run_id": raw_run_id,
                },
            )
            continue
        if run_id not in seen_run_ids:
            seen_run_ids.add(run_id)
            run_ids.append(run_id)
    return _AgentSubmissions(run_ids=tuple(run_ids), run_names=tuple(run_names))


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
    if settings.AGENT_ANTHROPIC_API_KEY and settings.AGENT_CLAUDE_USE_EXISTING_AUTH:
        return (
            "DSTACK_AGENT_ANTHROPIC_API_KEY and "
            "DSTACK_AGENT_CLAUDE_USE_EXISTING_AUTH cannot both be set."
        )
    if not settings.AGENT_ANTHROPIC_API_KEY and not _should_use_existing_claude_auth():
        return (
            "DSTACK_AGENT_ANTHROPIC_API_KEY is not set. Set it or opt in to existing "
            "Claude CLI auth with DSTACK_AGENT_CLAUDE_USE_EXISTING_AUTH=1."
        )
    if (
        settings.AGENT_CLAUDE_EFFORT is not None
        and settings.AGENT_CLAUDE_EFFORT not in _CLAUDE_EFFORT_LEVELS
    ):
        return f"DSTACK_AGENT_CLAUDE_EFFORT must be one of: {', '.join(_CLAUDE_EFFORT_LEVELS)}."
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


_existing_auth_warning_logged = False


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
        dstack_home_dir: Optional[Path] = None,
        endpoint_constraints: str = "",
        max_price: Optional[float] = None,
        spot_policy: Optional[str] = None,
        allowed_fleets: Sequence[str] = (),
        log_writer: Optional["_AgentLogWriter"] = None,
    ) -> None:
        self.root_dir = root_dir
        self.home_dir = home_dir
        self.dstack_home_dir = dstack_home_dir or home_dir
        self.work_dir = work_dir
        self.trace_path = trace_path
        self.env = env
        self.redacted_values = tuple(redacted_values)
        self.endpoint_name = endpoint_name
        self.model = model
        self.endpoint_constraints = endpoint_constraints
        self.max_price = max_price
        self.spot_policy = spot_policy
        self.allowed_fleets = tuple(allowed_fleets)
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
    install_skills: bool = True,
    agent_constraints: Optional[_EndpointAgentConstraints] = None,
) -> _AgentWorkspace:
    configuration = EndpointConfiguration.__response__.parse_raw(endpoint_model.configuration)
    endpoint_env = configuration.env.as_dict()
    if agent_constraints is None:
        agent_constraints = _get_static_endpoint_agent_constraints(configuration, endpoint_env)

    root_dir = workspace_root_dir
    home_dir = root_dir / "home"
    agent_home_dir = _prepare_agent_home_dir(root_dir=root_dir, home_dir=home_dir)
    work_dir = root_dir / "workspace"
    dstack_dir = home_dir / ".dstack"
    work_dir.mkdir(parents=True, exist_ok=True)
    dstack_dir.mkdir(parents=True, exist_ok=True)
    token = endpoint_model.user.token.get_plaintext_or_error()
    allowed_fleets = agent_constraints.allowed_fleets
    bin_dir = root_dir / _AGENT_BIN_DIR_NAME
    _write_cli_config(
        dstack_dir=dstack_dir,
        project_name=endpoint_model.project.name,
        server_url=settings.SERVER_URL,
        token=token,
    )

    env = _build_agent_env(
        home_dir=_get_claude_process_home_dir(agent_home_dir),
        project_name=endpoint_model.project.name,
        server_url=settings.SERVER_URL,
        token=token,
        endpoint_env=endpoint_env,
        bin_dir=bin_dir,
    )
    _warn_if_using_existing_claude_auth()
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
        dstack_home_dir=agent_home_dir,
        work_dir=work_dir,
        trace_path=trace_path,
        env=env,
        redacted_values=redacted_values,
        endpoint_name=endpoint_model.name,
        model=configuration.model,
        endpoint_constraints=agent_constraints.prompt_text,
        max_price=configuration.max_price,
        spot_policy=configuration.spot_policy.value if configuration.spot_policy else None,
        allowed_fleets=allowed_fleets,
        log_writer=_AgentLogWriter(
            project=endpoint_model.project,
            endpoint_id=endpoint_model.id,
            endpoint_name=endpoint_model.name,
        ),
    )
    workspace.env[_AGENT_PROGRESS_ENV] = str(workspace.progress_path)
    _install_agent_helper_scripts(workspace)
    if install_skills:
        _install_agent_skills(workspace)
    workspace.artifacts.initialize()
    return workspace


def _prepare_agent_home_dir(*, root_dir: Path, home_dir: Path) -> Path:
    home_dir.mkdir(parents=True, exist_ok=True)
    ssh_dir = home_dir / ".ssh"
    ssh_dir.mkdir(parents=True, exist_ok=True)
    ssh_dir.chmod(0o700)
    short_home_dir = _get_short_agent_home_dir(root_dir)
    short_home_dir.parent.mkdir(parents=True, exist_ok=True)
    if short_home_dir.is_symlink() and short_home_dir.resolve() == home_dir.resolve():
        return short_home_dir
    if short_home_dir.exists() or short_home_dir.is_symlink():
        if short_home_dir.is_dir() and not short_home_dir.is_symlink():
            shutil.rmtree(short_home_dir)
        else:
            short_home_dir.unlink()
    short_home_dir.symlink_to(home_dir, target_is_directory=True)
    return short_home_dir


def _get_claude_process_home_dir(agent_home_dir: Path) -> Path:
    if _should_use_existing_claude_auth():
        return Path.home()
    return agent_home_dir


def _get_short_agent_home_dir(root_dir: Path) -> Path:
    root_hash = hashlib.sha1(str(root_dir).encode()).hexdigest()[:8]
    return Path("/tmp") / f"dah-{root_hash}"


class _AgentArtifactRecorder:
    def __init__(self, workspace: _AgentWorkspace) -> None:
        self._workspace = workspace
        self._command_counter = 0

    def initialize(self) -> None:
        self._workspace.work_dir.mkdir(parents=True, exist_ok=True)
        self._command_counter = self._get_last_command_output_num()
        self._update_agent_state(phase="starting")
        for filename in [
            _AGENT_SUBMISSIONS_LOG_NAME,
            "commands.jsonl",
            _AGENT_PROGRESS_LOG_NAME,
        ]:
            (self._workspace.work_dir / filename).touch(exist_ok=True)

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
    server_url: str,
    token: str,
    endpoint_env: dict[str, str],
    bin_dir: Path,
) -> dict[str, str]:
    env = {name: value for name in _INHERITED_ENV_NAMES if (value := os.environ.get(name))}
    path = env.get("PATH", "")
    env["PATH"] = str(bin_dir) if not path else os.pathsep.join([str(bin_dir), path])
    env.update(
        {
            "HOME": str(home_dir),
            "DSTACK_PROJECT": project_name,
            "DSTACK_ENDPOINT_SERVER_URL": server_url,
            "DSTACK_ENDPOINT_BEARER_TOKEN": token,
        }
    )
    if settings.AGENT_ANTHROPIC_API_KEY:
        env["ANTHROPIC_API_KEY"] = settings.AGENT_ANTHROPIC_API_KEY
    elif _should_use_existing_claude_auth() and os.environ.get("USER"):
        env["USER"] = os.environ["USER"]
    env.update(endpoint_env)
    return env


async def _get_endpoint_agent_constraints(
    *,
    endpoint_model: EndpointModel,
    configuration: EndpointConfiguration,
) -> _EndpointAgentConstraints:
    endpoint_env = configuration.env.as_dict()
    allowed_fleets = await _get_endpoint_allowed_fleets(
        endpoint_model=endpoint_model,
        configuration=configuration,
    )
    return _EndpointAgentConstraints(
        prompt_text=_format_endpoint_constraints(
            configuration,
            endpoint_env,
            allowed_fleets=allowed_fleets,
        ),
        allowed_fleets=allowed_fleets,
    )


def _get_static_endpoint_agent_constraints(
    configuration: EndpointConfiguration,
    endpoint_env: dict[str, str],
) -> _EndpointAgentConstraints:
    allowed_fleets = _get_configured_endpoint_fleet_refs(configuration)
    return _EndpointAgentConstraints(
        prompt_text=_format_endpoint_constraints(
            configuration,
            endpoint_env,
            allowed_fleets=allowed_fleets,
        ),
        allowed_fleets=allowed_fleets,
    )


async def _get_endpoint_allowed_fleets(
    *,
    endpoint_model: EndpointModel,
    configuration: EndpointConfiguration,
) -> tuple[str, ...]:
    if configuration.fleets is not None and len(configuration.fleets) == 0:
        return ()
    configured_fleets = _get_configured_endpoint_fleet_refs(configuration)
    if configured_fleets:
        return configured_fleets

    async with get_session_ctx() as db_session:
        is_fleet_imported_subquery = exists().where(
            ImportModel.project_id == endpoint_model.project_id,
            ImportModel.export_id == ExportedFleetModel.export_id,
            ExportedFleetModel.fleet_id == FleetModel.id,
        )
        res = await db_session.execute(
            select(FleetModel.name, FleetModel.project_id, ProjectModel.name)
            .join(FleetModel.project)
            .where(
                FleetModel.deleted == False,
                FleetModel.status == FleetStatus.ACTIVE,
                or_(
                    FleetModel.project_id == endpoint_model.project_id,
                    is_fleet_imported_subquery,
                ),
            )
            .order_by(ProjectModel.name, FleetModel.name)
        )
        return tuple(
            name if project_id == endpoint_model.project_id else f"{project_name}/{name}"
            for name, project_id, project_name in res.all()
        )


def _get_configured_endpoint_fleet_refs(
    configuration: EndpointConfiguration,
) -> tuple[str, ...]:
    if not configuration.fleets:
        return ()
    return tuple(_format_constraint_value(fleet) for fleet in configuration.fleets)


def _get_endpoint_no_fleets_message(configuration: EndpointConfiguration) -> str:
    if configuration.fleets:
        return _ENDPOINT_NO_MATCHING_FLEETS_MESSAGE
    return _ENDPOINT_NO_FLEETS_MESSAGE


def _install_agent_helper_scripts(workspace: _AgentWorkspace) -> None:
    bin_dir = workspace.root_dir / _AGENT_BIN_DIR_NAME
    bin_dir.mkdir(parents=True, exist_ok=True)
    scripts = {
        "progress": _get_agent_progress_script(),
    }
    if _should_use_existing_claude_auth():
        scripts["dstack"] = _get_agent_home_script("dstack", workspace.dstack_home_dir)
        scripts["ssh"] = _get_agent_home_script("ssh", workspace.dstack_home_dir)
    for name, script in scripts.items():
        script_path = bin_dir / name
        script_path.write_text(script, encoding="utf-8")
        script_path.chmod(0o755)


def _get_agent_progress_script() -> str:
    return f"""#!{sys.executable}
import json
import os
from pathlib import Path
import sys

PROGRESS_ENV = "{_AGENT_PROGRESS_ENV}"


def main():
    message = " ".join(sys.argv[1:]).strip()
    if not message and not sys.stdin.isatty():
        message = sys.stdin.read().strip()
    if not message:
        print("Usage: progress <message>", file=sys.stderr)
        return 2
    path = Path(os.environ.get(PROGRESS_ENV, "progress.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({{"message": message}}, ensure_ascii=False) + "\\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""


def _get_agent_home_script(command: str, home_dir: Path) -> str:
    real_command = shutil.which(command)
    if real_command is None:
        return f"""#!{sys.executable}
import sys

print("Endpoint agent could not find the real {command} executable.", file=sys.stderr)
raise SystemExit(127)
"""
    return f"""#!{sys.executable}
import os
import sys

os.environ["HOME"] = {json.dumps(str(home_dir))}
os.execv({json.dumps(real_command)}, [{json.dumps(real_command)}, *sys.argv[1:]])
"""


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
            "json_schema": AGENT_FINAL_REPORT_JSON_SCHEMA,
        },
    }


def _build_prompt(workspace: _AgentWorkspace) -> str:
    return f"""{_load_endpoint_prompt()}

Endpoint request:
- name: {workspace.endpoint_name}
- model: {workspace.model}

{workspace.endpoint_constraints}
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
        skills_dir = parent / "skills"
        if (skills_dir / "dstack" / "SKILL.md").is_file():
            return skills_dir
    raise FileNotFoundError("Could not find packaged dstack skills")


def _format_endpoint_constraints(
    configuration: EndpointConfiguration,
    endpoint_env: dict[str, str],
    *,
    allowed_fleets: Sequence[str],
) -> str:
    lines = [
        "Fixed endpoint constraints:",
        "- Do not submit any task or service that conflicts with these values.",
        "- Put applicable fixed constraints into the final service YAML.",
    ]
    if configuration.max_price is not None:
        lines.append(f"- max_price: {configuration.max_price}")
    if configuration.spot_policy is not None:
        lines.append(f"- spot_policy: {configuration.spot_policy.value}")
    for field in ["backends", "regions", "availability_zones", "instance_types"]:
        values = getattr(configuration, field)
        if not values:
            continue
        formatted_values = [_format_constraint_value(value) for value in values]
        lines.append(f"- {field}: {', '.join(formatted_values)}")
    if allowed_fleets:
        lines.append(f"- fleets: {', '.join(allowed_fleets)}")
    if len(lines) == 3:
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
            return _AgentRunnerResult(error="Server agent failed before returning a final report")
        if returncode not in (0, None):
            return _AgentRunnerResult(
                error=(
                    "Server agent process exited without a final report "
                    f"(return code {returncode})"
                )
            )
        return _AgentRunnerResult(error="Server agent process exited without a final report")
    try:
        return _AgentRunnerResult(report=AgentFinalReport.parse_obj(process_output.report_data))
    except ValidationError as e:
        return _AgentRunnerResult(error=f"Server agent returned an invalid final report: {e}")


def _build_claude_command(request: dict[str, Any]) -> list[str]:
    options = request["options"]
    cmd = [
        _get_claude_executable() or "claude",
        "-p",
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
    if not _should_use_existing_claude_auth():
        cmd[2:2] = ["--bare"]
    else:
        cmd[2:2] = ["--setting-sources", "project,local"]
    if settings.AGENT_CLAUDE_EFFORT is not None:
        cmd[2:2] = ["--effort", settings.AGENT_CLAUDE_EFFORT]
    if options["max_turns"] is not None:
        cmd[2:2] = ["--max-turns", str(options["max_turns"])]
    return cmd


def _get_claude_executable() -> Optional[str]:
    if settings.AGENT_CLAUDE_PATH is not None:
        return shutil.which(settings.AGENT_CLAUDE_PATH)
    return shutil.which("claude")


def _should_use_existing_claude_auth() -> bool:
    return settings.AGENT_CLAUDE_USE_EXISTING_AUTH and not settings.AGENT_ANTHROPIC_API_KEY


def _warn_if_using_existing_claude_auth() -> None:
    global _existing_auth_warning_logged
    if not _should_use_existing_claude_auth() or _existing_auth_warning_logged:
        return
    logger.warning(
        "DSTACK_AGENT_CLAUDE_USE_EXISTING_AUTH=1 is enabled. This mode is intended "
        "only for local development. Production servers must set "
        "DSTACK_AGENT_ANTHROPIC_API_KEY. Claude will run without --bare and may read "
        "the server user's Claude CLI auth and settings."
    )
    _existing_auth_warning_logged = True


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
        await _process_agent_stream_line(
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
        await _process_agent_stream_line(
            line=line,
            workspace=workspace,
            stream_name=stream_name,
            output=output,
        )
    return output, new_offset


async def _process_agent_stream_line(
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
        message = _parse_agent_progress_log_message(line)
        if message is None:
            _write_trace_record(
                self._workspace,
                {"type": "agent-progress-ignored", "line": line},
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
    message = _parse_agent_progress_log_message(line)
    if message is None:
        _write_trace_record(
            workspace,
            {"type": "agent-progress-ignored", "line": line},
        )
        return
    await _write_agent_log(workspace, message)


def _parse_agent_progress_log_message(line: str) -> Optional[str]:
    try:
        parsed = json.loads(line)
    except json.JSONDecodeError:
        message = line.strip()
        return message or None
    return _format_agent_progress_log_message(parsed)


def _format_agent_progress_log_message(record: Any) -> Optional[str]:
    if isinstance(record, str):
        message = record.strip()
        return message or None
    if not isinstance(record, dict):
        return None
    message = record.get("message")
    if not isinstance(message, str) or not message.strip():
        return None
    return message.strip()


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
        "pgid": pid,
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
    agent_session: Optional[EndpointAgentSessionModel] = None,
) -> Optional[int]:
    state = _load_agent_process_state(workspace, agent_session=agent_session)
    if state is None:
        return None
    if state.host not in (None, _get_process_host()):
        return state.pid
    if _is_process_group_running(state.pgid):
        return state.pid
    _clear_agent_process_state(workspace, state.pid)
    return None


async def _abort_agent_session_process(
    *,
    agent_session: EndpointAgentSessionModel,
    workspace: _AgentWorkspace,
) -> bool:
    state = _load_agent_process_state(workspace, agent_session=agent_session)
    if state is None:
        return True
    if state.host not in (None, _get_process_host()):
        logger.info(
            "Endpoint agent process %s for endpoint %s is running on host %s; "
            "waiting for that host to abort it",
            state.pid,
            workspace.endpoint_name,
            state.host,
        )
        return False
    if not _is_process_group_running(state.pgid):
        _clear_agent_process_state(workspace, state.pid)
        return True

    logger.info(
        "Stopping endpoint agent process group %s for endpoint %s",
        state.pgid,
        workspace.endpoint_name,
    )
    _write_trace_record(
        workspace,
        {
            "type": "agent-process-abort-requested",
            "pid": state.pid,
            "pgid": state.pgid,
            "host": state.host,
        },
    )
    if not await _terminate_process_group(state.pgid):
        return False
    _clear_agent_process_state(workspace, state.pid)
    return True


async def _terminate_process_group(pgid: int) -> bool:
    if not _send_process_group_signal(pgid, signal.SIGTERM):
        return True
    await asyncio.sleep(_AGENT_PROCESS_ABORT_GRACE_SECONDS)
    if not _is_process_group_running(pgid):
        return True
    _send_process_group_signal(pgid, _get_kill_signal())
    await asyncio.sleep(0)
    return not _is_process_group_running(pgid)


def _send_process_group_signal(pgid: int, sig: signal.Signals) -> bool:
    killpg: Optional[Callable[[int, signal.Signals], None]] = getattr(os, "killpg", None)
    try:
        if killpg is not None:
            killpg(pgid, sig)
        else:
            os.kill(pgid, sig)
    except ProcessLookupError:
        return False
    except PermissionError:
        logger.warning("Permission denied while signaling process group %s", pgid)
        return True
    return True


def _load_agent_process_state(
    workspace: _AgentWorkspace,
    agent_session: Optional[EndpointAgentSessionModel] = None,
) -> Optional[_AgentProcessState]:
    path = workspace.work_dir / _AGENT_PROCESS_STATE_NAME
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            path.unlink(missing_ok=True)
            return None
        state = _parse_agent_process_state(data)
        if state is not None:
            return state
        path.unlink(missing_ok=True)
    if agent_session is None or agent_session.pid is None:
        return None
    return _AgentProcessState(
        pid=agent_session.pid,
        pgid=agent_session.pid,
        host=agent_session.process_host,
    )


def _parse_agent_process_state(data: Any) -> Optional[_AgentProcessState]:
    if not isinstance(data, dict):
        return None
    pid = data.get("pid")
    if not isinstance(pid, int):
        return None
    pgid = data.get("pgid", pid)
    if not isinstance(pgid, int):
        pgid = pid
    host = data.get("host")
    if not isinstance(host, str):
        host = None
    return _AgentProcessState(pid=pid, pgid=pgid, host=host)


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


def _is_process_group_running(pgid: int) -> bool:
    killpg: Optional[Callable[[int, int], None]] = getattr(os, "killpg", None)
    if killpg is None:
        return _is_process_running(pgid)
    try:
        killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        live_process_found = _has_non_zombie_process_in_group(pgid)
        return True if live_process_found is None else live_process_found
    return True


def _get_kill_signal() -> signal.Signals:
    return getattr(signal, "SIGKILL", signal.SIGTERM)


def _has_non_zombie_process_in_group(pgid: int) -> Optional[bool]:
    try:
        result = subprocess.run(
            ["ps", "-axo", "pgid=,stat="],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    found_group = False
    for line in result.stdout.splitlines():
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        try:
            line_pgid = int(parts[0])
        except ValueError:
            continue
        if line_pgid != pgid:
            continue
        found_group = True
        stat = parts[1].strip()
        if stat and not stat.startswith("Z"):
            return True
    return False if found_group else False


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
