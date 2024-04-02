import asyncio
import datetime
import logging
import os
from collections import deque
from functools import lru_cache
from typing import ClassVar, Deque, Dict, Iterable, Optional, TextIO

from pydantic import BaseModel, ValidationError

from dstack.gateway.common import run_async
from dstack.gateway.core.persistent import PersistentModel, get_persistent_state
from dstack.gateway.core.store import Service, StoreSubscriber
from dstack.gateway.stats.schemas import Stat

logger = logging.getLogger(__name__)
IGNORE_STATUSES = {403, 404}


class StatFrame(BaseModel):
    timestamp: int
    requests: int
    request_time: float


class LogEntry(BaseModel):
    timestamp: datetime.datetime
    host: str
    status: int
    request_time: float


class StatsCollector(PersistentModel, StoreSubscriber):
    """
    StatCollector parses nginx access log and calculates average request time and requests count.
    Its internal state could be serialized to a file and restored from it using pydantic.
    """

    persistent_key: ClassVar[str] = "stats_collector"

    path: str = "/var/log/nginx/dstack.access.log"
    resolution: int = 1
    ttl: int = 300
    services: Dict[str, str] = {}

    _stats: Dict[str, Deque[StatFrame]] = {}
    _file: Optional[TextIO] = None
    _lock = asyncio.Lock()

    async def collect(self) -> Dict[str, Dict[int, Stat]]:
        """
        :return: stats for each registered service with averaging over 30s, 1m, 5m
        """
        now = datetime.datetime.now(tz=datetime.timezone.utc).timestamp()
        output = {}
        async with self._lock:
            await run_async(self._collect)
            for service_id, host in self.services.items():
                output[service_id] = {
                    window: Stat(requests=0, request_time=0) for window in (30, 60, 300)
                }
                for window, stat in output[service_id].items():
                    # collect frames in the specified window
                    for frame in reversed(self._stats.get(host, [])):
                        if now - frame.timestamp > window:
                            break
                        stat.request_time += frame.request_time
                        stat.requests += frame.requests
                    if stat.requests > 0:
                        # apply average
                        stat.request_time /= stat.requests
        return output

    def _collect(self):
        now = datetime.datetime.now(tz=datetime.timezone.utc)

        for entry in self._read_access_log(now - datetime.timedelta(seconds=self.ttl)):
            if entry.status in IGNORE_STATUSES:
                continue

            frame_timestamp = int(entry.timestamp.timestamp() / self.resolution) * self.resolution
            if entry.host not in self._stats:
                self._stats[entry.host] = deque(maxlen=self.ttl // self.resolution)
            frames = self._stats[entry.host]

            # presume that log entries are sorted by timestamp
            if not frames or frames[-1].timestamp != frame_timestamp:
                self._stats[entry.host].append(
                    StatFrame(
                        timestamp=frame_timestamp, requests=1, request_time=entry.request_time
                    )
                )
            else:
                frames[-1].requests += 1
                frames[-1].request_time += (entry.request_time - frames[-1].request_time) / frames[
                    -1
                ].requests

        for host in list(self._stats.keys()):
            if self._stats[host][-1].timestamp < now.timestamp() - self.ttl:
                del self._stats[host]

    def _read_access_log(self, after: datetime.datetime) -> Iterable[LogEntry]:
        try:
            st_ino = os.stat(self.path).st_ino
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
                yield LogEntry.model_validate(
                    {
                        "timestamp": timestamp,
                        "host": host,
                        "status": status,
                        "request_time": request_time,
                    }
                )
            if os.fstat(self._file.fileno()).st_ino != st_ino:
                # file was rotated
                self._file.close()
                self._file = None

        if self._file is None and st_ino is not None:
            logger.info("Opening access log file: %s", self.path)
            self._file = open(self.path, "r")
            # normally, recursion will not exceed depth of 2
            yield from self._read_access_log(after)

    async def on_register(self, project: str, service: Service):
        # ignore project
        async with self._lock:
            self.services[service.id] = service.domain

    async def on_unregister(self, project: str, service_id: str):
        async with self._lock:
            del self.services[service_id]


@lru_cache()
def get_collector() -> StatsCollector:
    try:
        collector = StatsCollector.model_validate(
            get_persistent_state().get(StatsCollector.persistent_key, {})
        )
    except ValidationError as e:
        logger.warning("Failed to load stats collector state: %s", e)
        collector = StatsCollector()
    return collector
