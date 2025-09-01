import atexit
from typing import List, Optional
from uuid import UUID

from dstack._internal.core.models.logs import JobSubmissionLogs
from dstack._internal.server import settings
from dstack._internal.server.models import ProjectModel
from dstack._internal.server.schemas.logs import PollLogsRequest
from dstack._internal.server.schemas.runner import LogEvent as RunnerLogEvent
from dstack._internal.server.services.logs import aws as aws_logs
from dstack._internal.server.services.logs import gcp as gcp_logs
from dstack._internal.server.services.logs.base import (
    LogStorage,
    LogStorageError,
    b64encode_raw_message,
)
from dstack._internal.server.services.logs.filelog import FileLogStorage
from dstack._internal.utils.common import run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


_log_storage: Optional[LogStorage] = None


def get_log_storage() -> LogStorage:
    global _log_storage
    if _log_storage is not None:
        return _log_storage
    if settings.SERVER_CLOUDWATCH_LOG_GROUP:
        if aws_logs.BOTO_AVAILABLE:
            try:
                _log_storage = aws_logs.CloudWatchLogStorage(
                    group=settings.SERVER_CLOUDWATCH_LOG_GROUP,
                    region=settings.SERVER_CLOUDWATCH_LOG_REGION,
                )
            except LogStorageError as e:
                logger.error("Failed to initialize CloudWatch Logs storage: %s", e)
            except Exception:
                logger.exception("Got exception when initializing CloudWatch Logs storage")
            else:
                logger.debug("Using CloudWatch Logs storage")
        else:
            logger.error("Cannot use CloudWatch Logs storage: boto3 is not installed")
    elif settings.SERVER_GCP_LOGGING_PROJECT:
        if gcp_logs.GCP_LOGGING_AVAILABLE:
            try:
                _log_storage = gcp_logs.GCPLogStorage(
                    project_id=settings.SERVER_GCP_LOGGING_PROJECT
                )
            except LogStorageError as e:
                logger.error("Failed to initialize GCP Logs storage: %s", e)
            except Exception:
                logger.exception("Got exception when initializing GCP Logs storage")
            else:
                logger.debug("Using GCP Logs storage")
        else:
            logger.error("Cannot use GCP Logs storage: GCP deps are not installed")
    if _log_storage is None:
        _log_storage = FileLogStorage()
        logger.debug("Using file-based storage")
    atexit.register(_log_storage.close)
    return _log_storage


def write_logs(
    project: ProjectModel,
    run_name: str,
    job_submission_id: UUID,
    runner_logs: List[RunnerLogEvent],
    job_logs: List[RunnerLogEvent],
) -> None:
    return get_log_storage().write_logs(
        project=project,
        run_name=run_name,
        job_submission_id=job_submission_id,
        runner_logs=runner_logs,
        job_logs=job_logs,
    )


async def poll_logs_async(project: ProjectModel, request: PollLogsRequest) -> JobSubmissionLogs:
    job_submission_logs = await run_async(
        get_log_storage().poll_logs, project=project, request=request
    )
    # Logs are stored in plaintext but transmitted in base64 for API/CLI backward compatibility.
    # Old logs stored in base64 are encoded twice for transmission and shown as base64 in CLI/UI.
    # We live with that.
    # TODO: Drop base64 encoding in 0.20.
    for log_event in job_submission_logs.logs:
        log_event.message = b64encode_raw_message(log_event.message.encode())
    return job_submission_logs
