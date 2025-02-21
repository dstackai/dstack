import atexit
from typing import List, Optional
from uuid import UUID

from dstack._internal.core.models.logs import JobSubmissionLogs
from dstack._internal.server import settings
from dstack._internal.server.models import ProjectModel
from dstack._internal.server.schemas.logs import PollLogsRequest
from dstack._internal.server.schemas.runner import LogEvent as RunnerLogEvent
from dstack._internal.server.services.logs.aws import BOTO_AVAILABLE, CloudWatchLogStorage
from dstack._internal.server.services.logs.base import LogStorage, LogStorageError
from dstack._internal.server.services.logs.filelog import FileLogStorage
from dstack._internal.server.services.logs.gcp import GCP_LOGGING_AVAILABLE, GCPLogStorage
from dstack._internal.utils.common import run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


_log_storage: Optional[LogStorage] = None


def get_log_storage() -> LogStorage:
    global _log_storage
    if _log_storage is not None:
        return _log_storage
    if settings.SERVER_CLOUDWATCH_LOG_GROUP:
        if BOTO_AVAILABLE:
            try:
                _log_storage = CloudWatchLogStorage(
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
        if GCP_LOGGING_AVAILABLE:
            try:
                _log_storage = GCPLogStorage(project_id=settings.SERVER_GCP_LOGGING_PROJECT)
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
    return await run_async(get_log_storage().poll_logs, project=project, request=request)
