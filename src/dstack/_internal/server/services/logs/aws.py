import itertools
import operator
import urllib
import urllib.parse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator, List, Optional, Set, Tuple, TypedDict
from uuid import UUID

from dstack._internal.core.models.logs import (
    JobSubmissionLogs,
    LogEvent,
    LogEventSource,
    LogProducer,
)
from dstack._internal.server.models import ProjectModel
from dstack._internal.server.schemas.logs import PollLogsRequest
from dstack._internal.server.schemas.runner import LogEvent as RunnerLogEvent
from dstack._internal.server.services.logs.base import (
    LogStorage,
    LogStorageError,
    datetime_to_unix_time_ms,
    unix_time_ms_to_datetime,
)
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


BOTO_AVAILABLE = True
try:
    import boto3
    import botocore.exceptions
except ImportError:
    BOTO_AVAILABLE = False
else:

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
        # Maximum number of retries when polling for log events to skip empty pages.
        MAX_RETRIES = 10

        def __init__(self, *, group: str, region: Optional[str] = None) -> None:
            with self._wrap_boto_errors():
                session = boto3.Session(region_name=region)
                self._client = session.client("logs")
                self._check_group_exists(group)
            self._group = group
            self._region = self._client.meta.region_name
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
            next_token: Optional[str] = None
            with self._wrap_boto_errors():
                try:
                    cw_events, next_token = self._get_log_events_with_retry(stream, request)
                except botocore.exceptions.ClientError as e:
                    if not self._is_resource_not_found_exception(e):
                        raise
                    # Check if the group exists to distinguish between group not found vs stream not found
                    try:
                        self._check_group_exists(self._group)
                        # Group exists, so the error must be due to missing stream
                        logger.debug("Stream %s not found, returning dummy response", stream)
                        cw_events = []
                    except LogStorageError:
                        # Group doesn't exist, re-raise the LogStorageError
                        raise
            logs = [
                LogEvent(
                    timestamp=unix_time_ms_to_datetime(cw_event["timestamp"]),
                    log_source=LogEventSource.STDOUT,
                    message=cw_event["message"],
                )
                for cw_event in cw_events
            ]
            return JobSubmissionLogs(
                logs=logs,
                external_url=self._get_stream_external_url(stream),
                next_token=next_token,
            )

        def _get_log_events_with_retry(
            self, stream: str, request: PollLogsRequest
        ) -> Tuple[List[_CloudWatchLogEvent], Optional[str]]:
            current_request = request
            previous_next_token = request.next_token
            next_token = None

            for _ in range(self.MAX_RETRIES):
                cw_events, next_token = self._get_log_events(stream, current_request)

                if cw_events:
                    return cw_events, next_token

                if not next_token or next_token == previous_next_token:
                    return [], None

                previous_next_token = next_token
                current_request = PollLogsRequest(
                    run_name=request.run_name,
                    job_submission_id=request.job_submission_id,
                    start_time=request.start_time,
                    end_time=request.end_time,
                    descending=request.descending,
                    next_token=next_token,
                    limit=request.limit,
                    diagnose=request.diagnose,
                )

            if not request.descending:
                logger.debug(
                    "Stream %s: exhausted %d retries without finding logs, returning empty response",
                    stream,
                    self.MAX_RETRIES,
                )
            # Only return the next token after exhausting retries if going descending—
            # AWS CloudWatch guarantees more logs in that case. In ascending mode,
            # next token is always returned, even if no logs remain.
            # So descending works reliably; ascending has limits if gaps are too large.
            # In the future, UI/CLI should handle retries, and we can return next token for ascending too.
            return [], next_token if request.descending else None

        def _get_log_events(
            self, stream: str, request: PollLogsRequest
        ) -> Tuple[List[_CloudWatchLogEvent], Optional[str]]:
            start_from_head = not request.descending
            parameters = {
                "logGroupName": self._group,
                "logStreamName": stream,
                "limit": request.limit,
                "startFromHead": start_from_head,
            }

            if request.start_time:
                parameters["startTime"] = datetime_to_unix_time_ms(request.start_time)

            if request.end_time:
                parameters["endTime"] = datetime_to_unix_time_ms(request.end_time)
            elif start_from_head:
                # When startFromHead=true and no endTime is provided, set endTime to "now"
                # to prevent infinite pagination as new logs arrive faster than we can read them
                parameters["endTime"] = datetime_to_unix_time_ms(datetime.now(timezone.utc))

            if request.next_token:
                parameters["nextToken"] = request.next_token

            response = self._client.get_log_events(**parameters)

            events = response.get("events", [])
            next_token_key = "nextForwardToken" if start_from_head else "nextBackwardToken"
            next_token = response.get(next_token_key)

            # TODO: The code below is not going to be used until we migrate from base64-encoded logs to plain text logs.
            if request.descending:
                events = list(reversed(events))

            return events, next_token

        def _get_stream_external_url(self, stream: str) -> str:
            quoted_group = urllib.parse.quote(self._group, safe="")
            quoted_stream = urllib.parse.quote(stream, safe="")
            return f"https://console.aws.amazon.com/cloudwatch/home?region={self._region}#logsV2:log-groups/log-group/{quoted_group}/log-events/{quoted_stream}"

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
                message_size = len(event.message) + self.MESSAGE_OVERHEAD_SIZE
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
                logger.error(
                    "Stream %s: skipping %d future event(s)", stream, skipped_future_events
                )
            return batch, excessive_event

        def _runner_log_event_to_cloudwatch_event(
            self, runner_log_event: RunnerLogEvent
        ) -> _CloudWatchLogEvent:
            return {
                "timestamp": runner_log_event.timestamp,
                "message": runner_log_event.message.decode(errors="replace"),
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
