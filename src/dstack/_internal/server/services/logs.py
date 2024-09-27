import atexit
import base64
import itertools
import operator
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, List, Optional, Set, Tuple, TypedDict, Union
from uuid import UUID

from dstack._internal.core.errors import DstackError
from dstack._internal.core.models.logs import (
    JobSubmissionLogs,
    LogEvent,
    LogEventSource,
    LogProducer,
)
from dstack._internal.server import settings
from dstack._internal.server.models import ProjectModel
from dstack._internal.server.schemas.logs import PollLogsRequest
from dstack._internal.server.schemas.runner import LogEvent as RunnerLogEvent
from dstack._internal.server.utils.common import run_async
from dstack._internal.utils.logging import get_logger

BOTO_AVAILABLE = True
try:
    import boto3
    import botocore.exceptions
except ImportError:
    BOTO_AVAILABLE = False

logger = get_logger(__name__)


class LogStorageError(DstackError):
    pass


class LogStorage(ABC):
    @abstractmethod
    def poll_logs(self, project: ProjectModel, request: PollLogsRequest) -> JobSubmissionLogs:
        pass

    @abstractmethod
    def write_logs(
        self,
        project: ProjectModel,
        run_name: str,
        job_submission_id: UUID,
        runner_logs: List[RunnerLogEvent],
        job_logs: List[RunnerLogEvent],
    ) -> None:
        pass

    def close(self) -> None:
        pass


class _CloudWatchLogEvent(TypedDict):
    timestamp: int  # unix time in milliseconds
    message: str


class CloudWatchLogStorage(LogStorage):
    # "The maximum number of log events in a batch is 10,000".
    EVENT_MAX_COUNT_IN_BATCH = 10000
    # "The maximum batch size is 1,048,576 bytes" — exactly 1 MiB. "This size is calculated
    # as the sum of all event messages in UTF-8, plus 26 bytes for each log event".
    BATCH_MAX_SIZE = 1048576
    # "Each log event can be no larger than 256 KB" — KB means KiB; includes MESSAGE_OVERHEAD_SIZE.
    MESSAGE_MAX_SIZE = 262144
    # Message size in bytes = len(message.encode("utf-8")) + MESSAGE_OVERHEAD_SIZE.
    MESSAGE_OVERHEAD_SIZE = 26
    # "A batch of log events in a single request cannot span more than 24 hours".
    BATCH_MAX_SPAN = int(timedelta(hours=24).total_seconds()) * 1000
    # Decrease allowed deltas by possible clock drift between dstack and CloudWatch.
    CLOCK_DRIFT = int(timedelta(minutes=10).total_seconds()) * 1000
    # "None of the log events in the batch can be more than 14 days in the past."
    PAST_EVENT_MAX_DELTA = int((timedelta(days=14)).total_seconds()) * 1000 - CLOCK_DRIFT
    # "None of the log events in the batch can be more than 2 hours in the future."
    FUTURE_EVENT_MAX_DELTA = int((timedelta(hours=2)).total_seconds()) * 1000 - CLOCK_DRIFT

    def __init__(self, *, group: str, region: Optional[str] = None) -> None:
        with self._wrap_boto_errors():
            session = boto3.Session(region_name=region)
            self._client = session.client("logs")
            self._check_group_exists(group)
        self._group = group
        # Stores names of already created streams.
        # XXX: This set acts as an unbound cache. If this becomes a problem (in case of _very_ long
        # running server and/or lots of jobs, consider replacing it with an LRU cache, e.g.,
        # a simple OrderedDict-based implementation should be OK.
        self._streams: Set[str] = set()

    def close(self) -> None:
        self._client.close()

    def poll_logs(self, project: ProjectModel, request: PollLogsRequest) -> JobSubmissionLogs:
        log_producer = LogProducer.RUNNER if request.diagnose else LogProducer.JOB
        stream = self._get_stream_name(
            project.name, request.run_name, request.job_submission_id, log_producer
        )
        cw_events: List[_CloudWatchLogEvent]
        with self._wrap_boto_errors():
            try:
                cw_events = self._get_log_events(stream, request)
            except botocore.exceptions.ClientError as e:
                if not self._is_resource_not_found_exception(e):
                    raise
                logger.debug("Stream %s not found, returning dummy response", stream)
                cw_events = []
        cw_events_iter: Iterator[_CloudWatchLogEvent]
        if request.descending:
            # Regardless of the startFromHead value log events are arranged in chronological order,
            # from earliest to latest.
            cw_events_iter = reversed(cw_events)
        else:
            cw_events_iter = iter(cw_events)
        logs = [
            LogEvent(
                timestamp=_unix_time_ms_to_datetime(cw_event["timestamp"]),
                log_source=LogEventSource.STDOUT,
                message=cw_event["message"],
            )
            for cw_event in cw_events_iter
        ]
        return JobSubmissionLogs(logs=logs)

    def _get_log_events(self, stream: str, request: PollLogsRequest) -> List[_CloudWatchLogEvent]:
        parameters = {
            "logGroupName": self._group,
            "logStreamName": stream,
            "limit": request.limit,
        }
        start_from_head = not request.descending
        parameters["startFromHead"] = start_from_head
        if request.start_time:
            # XXX: Since callers use start_time/end_time for pagination, one millisecond is added
            # to avoid an infinite loop because startTime boundary is inclusive.
            parameters["startTime"] = _datetime_to_unix_time_ms(request.start_time) + 1
        if request.end_time:
            # No need to substract one millisecond in this case, though, seems that endTime is
            # exclusive, that is, time interval boundaries are [startTime, entTime)
            parameters["endTime"] = _datetime_to_unix_time_ms(request.end_time)
        response = self._client.get_log_events(**parameters)
        events: List[_CloudWatchLogEvent] = response["events"]
        if start_from_head or events:
            return events
        # Workaround for https://github.com/boto/boto3/issues/3718
        # Required only when startFromHead = false (the default value).
        next_token: str = response["nextBackwardToken"]
        # Limit max tries to avoid a possible infinite loop if the API is misbehaving
        tries_left = 10
        while tries_left:
            parameters["nextToken"] = next_token
            response = self._client.get_log_events(**parameters)
            events = response["events"]
            if events or response["nextBackwardToken"] == next_token:
                return events
            next_token = response["nextBackwardToken"]
            tries_left -= 1
        logger.warning("too many empty responses from stream %s, returning dummy response", stream)
        return []

    def write_logs(
        self,
        project: ProjectModel,
        run_name: str,
        job_submission_id: UUID,
        runner_logs: List[RunnerLogEvent],
        job_logs: List[RunnerLogEvent],
    ):
        if len(runner_logs) > 0:
            runner_stream = self._get_stream_name(
                project.name, run_name, job_submission_id, LogProducer.RUNNER
            )
            self._write_logs(
                stream=runner_stream,
                log_events=runner_logs,
            )
        if len(job_logs) > 0:
            jog_stream = self._get_stream_name(
                project.name, run_name, job_submission_id, LogProducer.JOB
            )
            self._write_logs(
                stream=jog_stream,
                log_events=job_logs,
            )

    def _write_logs(self, stream: str, log_events: List[RunnerLogEvent]) -> None:
        with self._wrap_boto_errors():
            self._ensure_stream_exists(stream)
            try:
                self._put_log_events(stream, log_events)
                return
            except botocore.exceptions.ClientError as e:
                if not self._is_resource_not_found_exception(e):
                    raise
                logger.debug("Stream %s not found, recreating", stream)
            # The stream is probably deleted due to retention policy, our cache is stale.
            self._ensure_stream_exists(stream, force=True)
            self._put_log_events(stream, log_events)

    def _put_log_events(self, stream: str, log_events: List[RunnerLogEvent]) -> None:
        # Python docs: "The built-in sorted() function is guaranteed to be stable."
        sorted_log_events = sorted(log_events, key=operator.attrgetter("timestamp"))
        if tuple(map(id, log_events)) != tuple(map(id, sorted_log_events)):
            logger.error(
                "Stream %s: events are not in chronological order, something wrong with runner",
                stream,
            )
        for batch in self._get_batch_iter(stream, sorted_log_events):
            self._client.put_log_events(
                logGroupName=self._group,
                logStreamName=stream,
                logEvents=batch,
            )

    def _get_batch_iter(
        self, stream: str, log_events: List[RunnerLogEvent]
    ) -> Iterator[List[_CloudWatchLogEvent]]:
        shared_event_iter = iter(log_events)
        event_iter = shared_event_iter
        while True:
            batch, excessive_event = self._get_next_batch(stream, event_iter)
            if not batch:
                return
            yield batch
            if excessive_event is not None:
                event_iter = itertools.chain([excessive_event], shared_event_iter)
            else:
                event_iter = shared_event_iter

    def _get_next_batch(
        self, stream: str, event_iter: Iterator[RunnerLogEvent]
    ) -> Tuple[List[_CloudWatchLogEvent], Optional[RunnerLogEvent]]:
        now_timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
        batch: List[_CloudWatchLogEvent] = []
        total_size = 0
        event_count = 0
        first_timestamp: Optional[int] = None
        skipped_past_events = 0
        skipped_future_events = 0
        # event that doesn't fit in the current batch
        excessive_event: Optional[RunnerLogEvent] = None
        for event in event_iter:
            # Normally there should not be empty messages.
            if not event.message:
                continue
            timestamp = event.timestamp
            if first_timestamp is None:
                first_timestamp = timestamp
            elif timestamp - first_timestamp > self.BATCH_MAX_SPAN:
                excessive_event = event
                break
            if now_timestamp - timestamp > self.PAST_EVENT_MAX_DELTA:
                skipped_past_events += 1
                continue
            if timestamp - now_timestamp > self.FUTURE_EVENT_MAX_DELTA:
                skipped_future_events += 1
                continue
            cw_event = self._runner_log_event_to_cloudwatch_event(event)
            # as message is base64-encoded, length in bytes = length in code points.
            message_size = len(cw_event["message"]) + self.MESSAGE_OVERHEAD_SIZE
            if message_size > self.MESSAGE_MAX_SIZE:
                # we should never hit this limit, as we use `io.Copy` to copy from pty to logs,
                # which under the hood uses 32KiB buffer, see runner/internal/executor/executor.go,
                # `execJob` -> `io.Copy(logger, ptmx)`
                logger.error(
                    "Stream %s: skipping event %d, message exceeds max size: %d > %d",
                    stream,
                    timestamp,
                    message_size,
                    self.MESSAGE_MAX_SIZE,
                )
                continue
            if total_size + message_size > self.BATCH_MAX_SIZE:
                excessive_event = event
                break
            batch.append(cw_event)
            total_size += message_size
            event_count += 1
            if event_count >= self.EVENT_MAX_COUNT_IN_BATCH:
                break
        if skipped_past_events > 0:
            logger.error("Stream %s: skipping %d past event(s)", stream, skipped_past_events)
        if skipped_future_events > 0:
            logger.error("Stream %s: skipping %d future event(s)", stream, skipped_future_events)
        return batch, excessive_event

    def _runner_log_event_to_cloudwatch_event(
        self, runner_log_event: RunnerLogEvent
    ) -> _CloudWatchLogEvent:
        return {
            "timestamp": runner_log_event.timestamp,
            "message": _b64encode_raw_message(runner_log_event.message),
        }

    @contextmanager
    def _wrap_boto_errors(self) -> Iterator[None]:
        try:
            yield
        except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError) as e:
            raise LogStorageError(f"CloudWatch Logs error: {type(e).__name__}: {e}") from e

    def _is_resource_not_found_exception(self, exc: "botocore.exceptions.ClientError") -> bool:
        try:
            return exc.response["Error"]["Code"] == "ResourceNotFoundException"
        except KeyError:
            return False

    def _check_group_exists(self, name: str) -> None:
        try:
            self._client.describe_log_streams(logGroupName=name, limit=1)
        except botocore.exceptions.ClientError as e:
            if self._is_resource_not_found_exception(e):
                raise LogStorageError(f"LogGroup '{name}' does not exist")
            raise

    def _ensure_stream_exists(self, name: str, *, force: bool = False) -> None:
        if not force and name in self._streams:
            return
        response = self._client.describe_log_streams(
            logGroupName=self._group, logStreamNamePrefix=name
        )
        for stream in response["logStreams"]:
            if stream["logStreamName"] == name:
                self._streams.add(name)
                return
        self._client.create_log_stream(logGroupName=self._group, logStreamName=name)
        self._streams.add(name)

    def _get_stream_name(
        self,
        project_name: str,
        run_name: str,
        job_submission_id: UUID,
        producer: LogProducer,
    ) -> str:
        return f"{project_name}/{run_name}/{job_submission_id}/{producer.value}"


class FileLogStorage(LogStorage):
    root: Path

    def __init__(self, root: Union[Path, str, None] = None) -> None:
        if root is None:
            self.root = settings.SERVER_DIR_PATH
        else:
            self.root = Path(root)

    def poll_logs(self, project: ProjectModel, request: PollLogsRequest) -> JobSubmissionLogs:
        # TODO Respect request.limit to support pagination
        log_producer = LogProducer.RUNNER if request.diagnose else LogProducer.JOB
        log_file_path = self._get_log_file_path(
            project_name=project.name,
            run_name=request.run_name,
            job_submission_id=request.job_submission_id,
            producer=log_producer,
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

    def write_logs(
        self,
        project: ProjectModel,
        run_name: str,
        job_submission_id: UUID,
        runner_logs: List[RunnerLogEvent],
        job_logs: List[RunnerLogEvent],
    ):
        if len(runner_logs) > 0:
            runner_log_file_path = self._get_log_file_path(
                project.name, run_name, job_submission_id, LogProducer.RUNNER
            )
            self._write_logs(
                log_file_path=runner_log_file_path,
                log_events=runner_logs,
            )
        if len(job_logs) > 0:
            job_log_file_path = self._get_log_file_path(
                project.name, run_name, job_submission_id, LogProducer.JOB
            )
            self._write_logs(
                log_file_path=job_log_file_path,
                log_events=job_logs,
            )

    def _write_logs(self, log_file_path: Path, log_events: List[RunnerLogEvent]) -> None:
        log_events_parsed = [self._runner_log_event_to_log_event(event) for event in log_events]
        log_file_path.parent.mkdir(exist_ok=True, parents=True)
        with open(log_file_path, "a") as f:
            f.writelines(log.json() + "\n" for log in log_events_parsed)

    def _get_log_file_path(
        self,
        project_name: str,
        run_name: str,
        job_submission_id: UUID,
        producer: LogProducer,
    ) -> Path:
        return (
            self.root
            / "projects"
            / project_name
            / "logs"
            / run_name
            / str(job_submission_id)
            / f"{producer.value}.log"
        )

    def _runner_log_event_to_log_event(self, runner_log_event: RunnerLogEvent) -> LogEvent:
        return LogEvent(
            timestamp=_unix_time_ms_to_datetime(runner_log_event.timestamp),
            log_source=LogEventSource.STDOUT,
            message=_b64encode_raw_message(runner_log_event.message),
        )


def _unix_time_ms_to_datetime(unix_time_ms: int) -> datetime:
    return datetime.fromtimestamp(unix_time_ms / 1000, tz=timezone.utc)


def _datetime_to_unix_time_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _b64encode_raw_message(message: bytes) -> str:
    return base64.b64encode(message).decode()


_default_log_storage: Optional[LogStorage] = None


def get_default_log_storage() -> LogStorage:
    global _default_log_storage
    if _default_log_storage is not None:
        return _default_log_storage
    if settings.SERVER_CLOUDWATCH_LOG_GROUP:
        if BOTO_AVAILABLE:
            try:
                _default_log_storage = CloudWatchLogStorage(
                    group=settings.SERVER_CLOUDWATCH_LOG_GROUP,
                    region=settings.SERVER_CLOUDWATCH_LOG_REGION,
                )
            except LogStorageError as e:
                logger.error("Failed to initialize CloudWatch Logs storage: %s", e)
            else:
                logger.debug("Using CloudWatch Logs storage")
        else:
            logger.error("Cannot use CloudWatch Logs storage, boto3 is not installed")
    if _default_log_storage is None:
        logger.debug("Using file-based storage")
        _default_log_storage = FileLogStorage()
    atexit.register(_default_log_storage.close)
    return _default_log_storage


def poll_logs(project: ProjectModel, request: PollLogsRequest) -> JobSubmissionLogs:
    return get_default_log_storage().poll_logs(project=project, request=request)


def write_logs(
    project: ProjectModel,
    run_name: str,
    job_submission_id: UUID,
    runner_logs: List[RunnerLogEvent],
    job_logs: List[RunnerLogEvent],
) -> None:
    return get_default_log_storage().write_logs(
        project=project,
        run_name=run_name,
        job_submission_id=job_submission_id,
        runner_logs=runner_logs,
        job_logs=job_logs,
    )


async def poll_logs_async(project: ProjectModel, request: PollLogsRequest) -> JobSubmissionLogs:
    return await run_async(get_default_log_storage().poll_logs, project=project, request=request)


async def write_logs_async(
    project: ProjectModel,
    run_name: str,
    job_submission_id: UUID,
    runner_logs: List[RunnerLogEvent],
    job_logs: List[RunnerLogEvent],
) -> None:
    return await run_async(
        get_default_log_storage().write_logs,
        project=project,
        run_name=run_name,
        job_submission_id=job_submission_id,
        runner_logs=runner_logs,
        job_logs=job_logs,
    )
