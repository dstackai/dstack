"""Single-owner, atomic local checkpoint storage for minute usage batches."""

import asyncio
import fcntl
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from dstack._internal.proxy.lib.cancellation import await_completion
from dstack._internal.proxy.lib.schemas.usage import LegacyUsageCheckpoint, UsageCheckpoint

_INITIALIZED = "usage-state-v2"


class MeteringStore:
    def __init__(self, path: Path, max_bytes: int = 64 * 1024 * 1024):
        self.path = path
        self.max_bytes = max_bytes
        self._marker = path.with_suffix(path.suffix + ".initialized")
        self._owner_fd: int | None = None
        self._write_lock = asyncio.Lock()

    def exists(self) -> bool:
        return self.path.exists() or self._marker.exists()

    def load(self) -> UsageCheckpoint | None:
        self._ensure_owner()
        if not self.path.exists():
            if self._marker.exists():
                raise ValueError(
                    "Initialized usage checkpoint is missing; reconcile before restart"
                )
            return None
        with self.path.open("rb") as source:
            raw = source.read(self.max_bytes + 1)
        if len(raw) > self.max_bytes:
            raise ValueError("Usage checkpoint exceeds size limit")
        data = json.loads(raw, object_pairs_hook=_unique_object)
        if not isinstance(data, dict):
            raise ValueError("Usage checkpoint must be an object")
        marker = self._read_marker()
        if data.get("schema_version", 1) == 1:
            legacy = LegacyUsageCheckpoint.model_validate(data)
            if marker is not None and marker != legacy.collector_id:
                raise ValueError("Legacy usage identity mismatch")
            state = UsageCheckpoint.model_validate(
                legacy.model_dump(exclude={"schema_version", "collector_id"})
            )
            self._save(state)
        else:
            state = UsageCheckpoint.model_validate(data)
            if marker != _INITIALIZED:
                # Recovery after checkpoint replacement but before marker replacement.
                self._save(state)
        return state

    def _read_marker(self) -> str | None:
        if not self._marker.exists():
            return None
        marker = self._marker.read_text()
        if marker != _INITIALIZED:
            try:
                if uuid.UUID(marker).hex != marker:
                    raise ValueError("Non-canonical legacy marker")
            except ValueError as exc:
                raise ValueError("Invalid usage initialized marker") from exc
        return marker

    async def save(self, state: UsageCheckpoint) -> None:
        # Deep copy before crossing the thread boundary; the writer owns a consistent snapshot.
        snapshot = state.model_copy(deep=True)
        async with self._write_lock:
            writer = asyncio.create_task(asyncio.to_thread(self._save, snapshot))
            # The thread survives Task.cancel(); keep ownership until it actually finishes,
            # even if shutdown or an HTTP disconnect cancels this coroutine repeatedly.
            await await_completion(writer)

    def close(self) -> None:
        if self._owner_fd is not None:
            os.close(self._owner_fd)
            self._owner_fd = None

    def _ensure_owner(self) -> None:
        if self._owner_fd is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(fd)
            raise
        self._owner_fd = fd

    def _save(self, state: UsageCheckpoint) -> None:
        self._ensure_owner()
        raw = state.model_dump_json().encode()
        if len(raw) > self.max_bytes:
            raise OSError("Usage checkpoint exceeds storage limit")
        marker = self._read_marker()
        self._atomic_write(self.path, raw)
        if marker != _INITIALIZED:
            self._atomic_write(self._marker, _INITIALIZED.encode())

    @staticmethod
    def _atomic_write(path: Path, raw: bytes) -> None:
        fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as target:
                target.write(raw)
                target.flush()
                os.fsync(target.fileno())
            os.replace(name, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(name):
                os.unlink(name)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate checkpoint field: {key}")
        result[key] = value
    return result
