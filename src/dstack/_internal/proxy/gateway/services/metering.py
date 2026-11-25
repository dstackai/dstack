import asyncio
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from dstack._internal.proxy.gateway.schemas.metering import MeteringBatch, MeteringRecord
from dstack._internal.proxy.lib.auth import ProxyCaller
from dstack._internal.proxy.lib.metering import BaseProxyMeter
from dstack._internal.proxy.lib.models import Service
from dstack._internal.utils.common import get_current_datetime, run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

FLUSH_INTERVAL = 5
"""Seconds between writing the counters to batch files."""
BATCH_TTL = timedelta(days=7)
"""Batch files that the server has not collected are deleted after this time."""
OLD_BATCHES_CLEANUP_INTERVAL = 3600
LAST_BATCH_NO_FILE_NAME = "last_batch_no"


@dataclass(frozen=True)
class MeteringRecordKey:
    hour: datetime
    """UTC, start of the hour in which the tokens were counted."""
    project_id: uuid.UUID
    user_id: uuid.UUID
    run_id: uuid.UUID
    export_id: Optional[uuid.UUID]
    """The export that the requests came through. `None` for a project's own models."""


@dataclass
class MeteringRecordValue:
    input_tokens: int = 0
    """Includes `cached_input_tokens`."""
    cached_input_tokens: int = 0
    output_tokens: int = 0


class GatewayProxyMeter(BaseProxyMeter):
    """
    Counts tokens in memory. `flush` moves the counters to a new batch file in `dir`.
    The server collects the batches in the order of their numbers
    and confirms the ones it has saved by asking for later ones.
    """

    def __init__(self, dir: Path) -> None:
        self._dir = dir
        self._counters: dict[MeteringRecordKey, MeteringRecordValue] = {}
        # Batch numbers are never reused, even after a restart with all batch files collected,
        # since the server only asks for batches with numbers above the ones it has saved.
        self._last_batch_no = max([self._read_last_batch_no(), *self._list_batch_nos()])
        self._files_lock = asyncio.Lock()
        self._next_old_batches_cleanup_at = time.monotonic()
        self._services_without_id: set[str] = set()

    def add(
        self,
        caller: ProxyCaller,
        service: Service,
        export_id: Optional[str],
        input_tokens: int,
        cached_input_tokens: int,
        output_tokens: int,
    ) -> None:
        if service.id is None:
            if service.fmt() not in self._services_without_id:
                self._services_without_id.add(service.fmt())
                logger.warning("Service %s has no ID, cannot meter its tokens", service.fmt())
            return
        key = MeteringRecordKey(
            hour=get_current_datetime().replace(minute=0, second=0, microsecond=0),
            project_id=caller.project_id,
            user_id=caller.user_id,
            run_id=uuid.UUID(service.id),
            export_id=uuid.UUID(export_id) if export_id is not None else None,
        )
        self._add(key, MeteringRecordValue(input_tokens, cached_input_tokens, output_tokens))

    async def flush(self) -> None:
        """
        Writes the counters, if any, to a new batch file and resets them.
        Once in `OLD_BATCHES_CLEANUP_INTERVAL`, also deletes the batch files older than `BATCH_TTL`.
        """
        if time.monotonic() >= self._next_old_batches_cleanup_at:
            self._next_old_batches_cleanup_at = time.monotonic() + OLD_BATCHES_CLEANUP_INTERVAL
            async with self._files_lock:
                await run_async(self._delete_old_batches)
        if not self._counters:
            return
        counters, self._counters = self._counters, {}
        try:
            async with self._files_lock:
                await run_async(self._write_batch, counters)
        except Exception:
            # Keep the counts for the next flush.
            for key, value in counters.items():
                self._add(key, value)
            raise

    async def collect(self, after: int, limit: int) -> list[MeteringBatch]:
        """
        Returns up to `limit` batches with numbers above `after`, oldest first,
        and deletes the batches up to `after`, which the server has saved.
        """
        async with self._files_lock:
            return await run_async(self._collect, after, limit)

    def _add(self, key: MeteringRecordKey, value: MeteringRecordValue) -> None:
        counter = self._counters.setdefault(key, MeteringRecordValue())
        counter.input_tokens += value.input_tokens
        counter.cached_input_tokens += value.cached_input_tokens
        counter.output_tokens += value.output_tokens

    def _write_batch(self, counters: dict[MeteringRecordKey, MeteringRecordValue]) -> None:
        batch = MeteringBatch(
            batch_no=self._last_batch_no + 1,
            created_at=get_current_datetime(),
            records=[
                MeteringRecord(
                    hour=key.hour,
                    project_id=key.project_id,
                    user_id=key.user_id,
                    run_id=key.run_id,
                    export_id=key.export_id,
                    input_tokens=value.input_tokens,
                    cached_input_tokens=value.cached_input_tokens,
                    output_tokens=value.output_tokens,
                )
                for key, value in counters.items()
            ],
        )
        self._write_last_batch_no(batch.batch_no)
        self._write_file(self._get_batch_path(batch.batch_no), batch.model_dump_json())

    def _collect(self, after: int, limit: int) -> list[MeteringBatch]:
        if after > self._last_batch_no:
            # The server has saved batches that are no longer known here: the files were lost,
            # e.g. in a container restart. Number new batches above them,
            # or the server would never ask for them.
            self._write_last_batch_no(after)
        batches = []
        for batch_no in self._list_batch_nos():
            path = self._get_batch_path(batch_no)
            if batch_no <= after:
                path.unlink(missing_ok=True)
                continue
            if len(batches) == limit:
                break
            try:
                batches.append(MeteringBatch.model_validate_json(path.read_text()))
            except ValidationError:
                logger.exception("Skipping invalid metering batch %s", path)
        return batches

    def _delete_old_batches(self) -> None:
        min_modified_at = (get_current_datetime() - BATCH_TTL).timestamp()
        for batch_no in self._list_batch_nos():
            path = self._get_batch_path(batch_no)
            if path.stat().st_mtime >= min_modified_at:
                # Batches are written in the order of their numbers.
                break
            path.unlink()

    def _read_last_batch_no(self) -> int:
        try:
            return int((self._dir / LAST_BATCH_NO_FILE_NAME).read_text())
        except (FileNotFoundError, ValueError):
            return 0

    def _write_last_batch_no(self, batch_no: int) -> None:
        self._write_file(self._dir / LAST_BATCH_NO_FILE_NAME, str(batch_no))
        self._last_batch_no = batch_no

    def _list_batch_nos(self) -> list[int]:
        if not self._dir.exists():
            return []
        return sorted(int(path.stem) for path in self._dir.glob("*.json") if path.stem.isdigit())

    def _get_batch_path(self, batch_no: int) -> Path:
        return self._dir / f"{batch_no}.json"

    def _write_file(self, path: Path, content: str) -> None:
        """Writes the file atomically."""
        self._dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", dir=self._dir, delete=False) as f:
            temporary_path = Path(f.name)
            try:
                f.write(content)
                f.close()
                temporary_path.replace(path)
            finally:
                temporary_path.unlink(missing_ok=True)
