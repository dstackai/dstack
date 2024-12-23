import asyncio
import datetime
import logging
import os
from collections import deque
from collections.abc import Reversible
from pathlib import Path
from typing import Iterable, Optional, TextIO

from pydantic import BaseModel

from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.gateway.schemas.stats import PerWindowStats, ServiceStats, Stat
from dstack._internal.utils.common import run_async

logger = logging.getLogger(__name__)
IGNORE_STATUSES = {403, 404}
WINDOWS = (30, 60, 300)
TTL = WINDOWS[-1]
EMPTY_STATS = {window: Stat(requests=0, request_time=0.0) for window in WINDOWS}


class StatFrame(BaseModel):
    """Service metrics aggregated over a 1s frame"""

    timestamp: int
    requests: int
    requests_time_total: float


class LogEntry(BaseModel):
    """A line from the access log"""

    timestamp: datetime.datetime
    host: str
    status: int
    request_time: float


class StatsCollector:
    """
    StatCollector parses nginx access log and calculates average request time and requests count.
    """

    def __init__(self, access_log: Path) -> None:
        self._path = access_log
        self._file: Optional[TextIO] = None
        self._stats: dict[str, deque[StatFrame]] = {}
        self._lock = asyncio.Lock()

    async def collect(self) -> dict[str, PerWindowStats]:
        """
        :return: stats per host aggregated by 30s, 1m, 5m
        """
        result = {}
        async with self._lock:
            await run_async(self._collect)
            now = datetime.datetime.now(tz=datetime.timezone.utc)
            for host, frames in self._stats.items():
                result[host] = self._aggregate(frames, now)
        return result

    @staticmethod
    def _aggregate(frames: Reversible[StatFrame], now: datetime.datetime) -> PerWindowStats:
        """
        Aggregate 1s `frames` into windows 30s, 1m, 5m before `now`
        """
        result = {}
        for window in WINDOWS:
            req_count = 0
            req_time_total = 0.0
            for frame in reversed(frames):
                if now.timestamp() - frame.timestamp > window:
                    break
                req_time_total += frame.requests_time_total
                req_count += frame.requests
            if req_count > 0:
                result[window] = Stat(
                    requests=req_count,
                    request_time=round(req_time_total / req_count, 3),
                )
            else:
                result[window] = Stat(requests=0, request_time=0.0)
        return result

    def _collect(self) -> None:
        now = datetime.datetime.now(tz=datetime.timezone.utc)

        for entry in self._read_access_log(now - datetime.timedelta(seconds=TTL)):
            if entry.status in IGNORE_STATUSES:
                continue

            frame_timestamp = int(entry.timestamp.timestamp())
            frames = self._stats.setdefault(entry.host, deque(maxlen=TTL))

            # presume that log entries are sorted by timestamp
            if not frames or frames[-1].timestamp != frame_timestamp:
                latest_frame = StatFrame(
                    timestamp=frame_timestamp, requests=1, requests_time_total=entry.request_time
                )
                frames.append(latest_frame)
            else:
                latest_frame = frames[-1]
                latest_frame.requests += 1
                latest_frame.requests_time_total += entry.request_time

        for host in list(self._stats.keys()):
            if self._stats[host][-1].timestamp < now.timestamp() - TTL:
                del self._stats[host]

    def _read_access_log(self, after: datetime.datetime) -> Iterable[LogEntry]:
        try:
            st_ino = os.stat(self._path).st_ino
        except FileNotFoundError:
            st_ino = None

        if self._file is not None:
            while True:
                line = self._file.readline()
                if not line:
                    break
                timestamp_str, host, status, request_time = line.split()
                timestamp = datetime.datetime.fromisoformat(timestamp_str)
                if timestamp < after:
                    continue
                yield LogEntry(
                    timestamp=timestamp,
                    host=host,
                    status=int(status),
                    request_time=float(request_time),
                )
            if os.fstat(self._file.fileno()).st_ino != st_ino:
                # file was rotated
                self._file.close()
                self._file = None

        if self._file is None and st_ino is not None:
            logger.info("Opening access log file: %s", self._path)
            self._file = open(self._path, "r")
            # normally, recursion will not exceed depth of 2
            yield from self._read_access_log(after)


async def get_service_stats(
    repo: GatewayProxyRepo, collector: StatsCollector
) -> list[ServiceStats]:
    stats_per_host = await collector.collect()
    services = await repo.list_services()
    return [
        ServiceStats(
            project_name=service.project_name,
            run_name=service.run_name,
            stats=stats_per_host.get(service.domain_safe, EMPTY_STATS),
        )
        for service in services
    ]
