import base64
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from dstack._internal.core.models.endpoints import Endpoint
from dstack._internal.core.models.logs import LogEvent
from dstack._internal.server.schemas.logs import PollLogsRequest

_ENDPOINT_LOG_WATCH_OVERLAP = timedelta(seconds=20)


class EndpointLogPoller:
    def __init__(self, *, api, endpoint: Endpoint, start_time: Optional[datetime] = None) -> None:
        self._api = api
        self._endpoint = endpoint
        self._next_start_time = start_time
        self._latest_printed_at: Optional[datetime] = None
        self._seen_log_counts: Counter[tuple[datetime, str, str]] = Counter()

    def poll(self) -> list[bytes]:
        logs: list[bytes] = []
        next_token = None
        batch_log_counts: Counter[tuple[datetime, str, str]] = Counter()
        while True:
            resp = self._api.client.logs.poll(
                project_name=self._api.project,
                body=PollLogsRequest(
                    run_name=self._endpoint.name,
                    job_submission_id=self._endpoint.id,
                    start_time=self._next_start_time,
                    end_time=None,
                    descending=False,
                    limit=1000,
                    diagnose=False,
                    next_token=next_token,
                ),
            )
            for log in resp.logs:
                if not self._should_print(log, batch_log_counts=batch_log_counts):
                    continue
                logs.append(_format_log(log))
            next_token = resp.next_token
            if next_token is None:
                break
        if self._latest_printed_at is not None:
            self._next_start_time = self._latest_printed_at - _ENDPOINT_LOG_WATCH_OVERLAP
            self._cleanup_seen_log_counts(before=self._next_start_time)
        return logs

    def _should_print(
        self, log: LogEvent, *, batch_log_counts: Counter[tuple[datetime, str, str]]
    ) -> bool:
        key = _log_key(log)
        batch_log_counts[key] += 1
        if batch_log_counts[key] <= self._seen_log_counts[key]:
            return False
        self._seen_log_counts[key] += 1
        if self._latest_printed_at is None or log.timestamp > self._latest_printed_at:
            self._latest_printed_at = log.timestamp
        return True

    def _cleanup_seen_log_counts(self, before: datetime) -> None:
        for key in list(self._seen_log_counts):
            timestamp, _, _ = key
            if timestamp <= before:
                del self._seen_log_counts[key]


def _log_key(log: LogEvent) -> tuple[datetime, str, str]:
    return (log.timestamp, log.log_source.value, log.message)


def _format_log(log: LogEvent) -> bytes:
    timestamp = log.timestamp.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    return f"[{timestamp}] ".encode() + base64.b64decode(log.message)
