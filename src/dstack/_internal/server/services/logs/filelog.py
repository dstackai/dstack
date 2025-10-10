import os
from pathlib import Path
from typing import Generator, List, Optional, Tuple, Union
from uuid import UUID

from dstack._internal.core.errors import ServerClientError
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
from dstack._internal.server.services.logs.base import (
    LogStorage,
    unix_time_ms_to_datetime,
)


class FileLogStorage(LogStorage):
    root: Path

    def __init__(self, root: Union[Path, str, None] = None) -> None:
        if root is None:
            self.root = settings.SERVER_DIR_PATH
        else:
            self.root = Path(root)

    def poll_logs(self, project: ProjectModel, request: PollLogsRequest) -> JobSubmissionLogs:
        log_producer = LogProducer.RUNNER if request.diagnose else LogProducer.JOB
        log_file_path = self._get_log_file_path(
            project_name=project.name,
            run_name=request.run_name,
            job_submission_id=request.job_submission_id,
            producer=log_producer,
        )

        if request.descending:
            return self._poll_logs_descending(log_file_path, request)
        else:
            return self._poll_logs_ascending(log_file_path, request)

    def _poll_logs_ascending(
        self, log_file_path: Path, request: PollLogsRequest
    ) -> JobSubmissionLogs:
        start_line = 0
        if request.next_token:
            start_line = self._parse_next_token(request.next_token)

        logs = []
        next_token = None
        current_line = 0

        try:
            with open(log_file_path) as f:
                # Skip to start_line if needed
                for _ in range(start_line):
                    if f.readline() == "":
                        # File is shorter than start_line
                        return JobSubmissionLogs(logs=logs, next_token=next_token)
                    current_line += 1

                # Read lines one by one
                while True:
                    line = f.readline()
                    if line == "":  # EOF
                        break

                    current_line += 1

                    try:
                        log_event = LogEvent.__response__.parse_raw(line)
                    except Exception:
                        # Skip malformed lines
                        continue

                    if request.start_time and log_event.timestamp <= request.start_time:
                        continue
                    if request.end_time is not None and log_event.timestamp >= request.end_time:
                        break

                    logs.append(log_event)

                    if len(logs) >= request.limit:
                        # Check if there are more lines to read
                        if f.readline() != "":
                            next_token = str(current_line)
                        break
        except FileNotFoundError:
            pass

        return JobSubmissionLogs(logs=logs, next_token=next_token)

    def _poll_logs_descending(
        self, log_file_path: Path, request: PollLogsRequest
    ) -> JobSubmissionLogs:
        start_offset = None
        if request.next_token is not None:
            start_offset = self._parse_next_token(request.next_token)

        candidate_logs = []

        try:
            line_generator = self._read_lines_reversed(log_file_path, start_offset)

            for line_bytes, line_start_offset in line_generator:
                try:
                    line_str = line_bytes.decode("utf-8")
                    log_event = LogEvent.__response__.parse_raw(line_str)
                except Exception:
                    continue  # Skip malformed lines

                if request.end_time is not None and log_event.timestamp > request.end_time:
                    continue
                if request.start_time and log_event.timestamp <= request.start_time:
                    break

                candidate_logs.append((log_event, line_start_offset))

                if len(candidate_logs) > request.limit:
                    break
        except FileNotFoundError:
            return JobSubmissionLogs(logs=[], next_token=None)

        logs = [log for log, _ in candidate_logs[: request.limit]]
        next_token = None
        if len(candidate_logs) > request.limit:
            # We fetched one more than the limit, so there are more pages.
            # The next token should point to the start of the last log we are returning.
            _, last_log_offset = candidate_logs[request.limit - 1]
            next_token = str(last_log_offset)

        return JobSubmissionLogs(logs=logs, next_token=next_token)

    @staticmethod
    def _read_lines_reversed(
        filepath: Path, start_offset: Optional[int] = None, chunk_size: int = 8192
    ) -> Generator[Tuple[bytes, int], None, None]:
        """
        A generator that yields lines from a file in reverse order, along with the byte
        offset of the start of each line. This is memory-efficient for large files.
        """
        with open(filepath, "rb") as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            cursor = file_size

            # If a start_offset is provided, optimize by starting the read
            # from a more specific location instead of the end of the file.
            if start_offset is not None and start_offset < file_size:
                # To get the full content of the line that straddles the offset,
                # we need to find its end (the next newline character).
                f.seek(start_offset)
                chunk = f.read(chunk_size)
                newline_pos = chunk.find(b"\n")
                if newline_pos != -1:
                    # Found the end of the line. The cursor for reverse reading
                    # should start from this point to include the full line.
                    cursor = start_offset + newline_pos + 1
                else:
                    # No newline found, which means the rest of the file is one line.
                    # The default cursor pointing to file_size is correct.
                    pass

            buffer = b""

            while cursor > 0:
                seek_pos = max(0, cursor - chunk_size)
                amount_to_read = cursor - seek_pos
                f.seek(seek_pos)
                chunk = f.read(amount_to_read)
                cursor = seek_pos

                buffer = chunk + buffer

                while b"\n" in buffer:
                    newline_pos = buffer.rfind(b"\n")
                    line = buffer[newline_pos + 1 :]
                    line_start_offset = cursor + newline_pos + 1

                    # Skip lines that start at or after the start_offset
                    if start_offset is None or line_start_offset < start_offset:
                        yield line, line_start_offset

                    buffer = buffer[:newline_pos]

            # The remaining buffer is the first line of the file.
            # Only yield it if we're not using start_offset or if it starts before start_offset
            if buffer and (start_offset is None or 0 < start_offset):
                yield buffer, 0

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
            timestamp=unix_time_ms_to_datetime(runner_log_event.timestamp),
            log_source=LogEventSource.STDOUT,
            message=runner_log_event.message.decode(errors="replace"),
        )

    def _parse_next_token(self, next_token: str) -> int:
        if next_token is None:
            return None
        try:
            value = int(next_token)
            if value < 0:
                raise ValueError("Offset must be non-negative")
            return value
        except (ValueError, TypeError):
            raise ServerClientError(
                f"Invalid next_token: {next_token}. Must be a non-negative integer."
            )
