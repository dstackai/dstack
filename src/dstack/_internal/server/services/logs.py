import base64
from datetime import datetime, timezone
from pathlib import Path
from typing import List
from uuid import UUID

from dstack._internal.core.models.logs import JobSubmissionLogs, LogEvent, LogEventSource
from dstack._internal.server import settings
from dstack._internal.server.models import ProjectModel
from dstack._internal.server.schemas.logs import PollLogsRequest
from dstack._internal.server.schemas.runner import LogEvent as RunnerLogEvent


def write_logs(
    project: ProjectModel,
    run_name: str,
    job_submission_id: UUID,
    runner_logs: List[RunnerLogEvent],
    job_logs: List[RunnerLogEvent],
):
    if len(runner_logs) > 0:
        runner_log_file_path = _get_runner_log_file_path(
            project_name=project.name,
            run_name=run_name,
            job_submission_id=job_submission_id,
        )
        _write_logs(
            log_file_path=runner_log_file_path,
            log_events=runner_logs,
        )
    if len(job_logs) > 0:
        job_log_file_path = _get_job_log_file_path(
            project_name=project.name,
            run_name=run_name,
            job_submission_id=job_submission_id,
        )
        _write_logs(
            log_file_path=job_log_file_path,
            log_events=job_logs,
        )


def _write_logs(
    log_file_path: Path,
    log_events: List[RunnerLogEvent],
):
    log_events_parsed = [_runner_log_event_to_log_event(log) for log in log_events]
    log_file_path.parent.mkdir(exist_ok=True, parents=True)
    with open(log_file_path, "a") as f:
        f.writelines(log.json() + "\n" for log in log_events_parsed)


def poll_logs(
    project: ProjectModel,
    request: PollLogsRequest,
) -> JobSubmissionLogs:
    # TODO Respect request.limit to support pagination
    if request.diagnose:
        log_file_path = _get_runner_log_file_path(
            project_name=project.name,
            run_name=request.run_name,
            job_submission_id=request.job_submission_id,
        )
    else:
        log_file_path = _get_job_log_file_path(
            project_name=project.name,
            run_name=request.run_name,
            job_submission_id=request.job_submission_id,
        )
    logs = []
    try:
        with open(log_file_path) as f:
            for line in f:
                log_event = LogEvent.__response__.parse_raw(line)
                if request.start_time and log_event.timestamp <= request.start_time:
                    continue
                if request.end_time is None or log_event.timestamp < request.end_time:
                    logs.append(log_event)
                else:
                    break
    except IOError:
        pass
    if request.descending:
        logs = list(reversed(logs))
    return JobSubmissionLogs(logs=logs)


def _runner_log_event_to_log_event(runner_log_event: RunnerLogEvent) -> LogEvent:
    return LogEvent(
        timestamp=datetime.fromtimestamp(runner_log_event.timestamp / 1e9, tz=timezone.utc),
        log_source=LogEventSource.STDOUT,
        message=base64.b64encode(runner_log_event.message).decode(),
    )


def _get_job_log_file_path(project_name: str, run_name: str, job_submission_id: UUID) -> Path:
    return (
        settings.SERVER_DIR_PATH
        / "projects"
        / project_name
        / "logs"
        / run_name
        / str(job_submission_id)
        / "job.log"
    )


def _get_runner_log_file_path(project_name: str, run_name: str, job_submission_id: UUID) -> Path:
    return (
        settings.SERVER_DIR_PATH
        / "projects"
        / project_name
        / "logs"
        / run_name
        / str(job_submission_id)
        / "runner.log"
    )
