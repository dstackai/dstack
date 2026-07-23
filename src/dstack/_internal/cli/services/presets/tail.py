"""Offset-persistent tailers over the agent's stream and record files."""

import asyncio
import json
import threading
from contextlib import suppress
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from dstack._internal.cli.services.presets.redaction import redact
from dstack._internal.cli.services.presets.session import (
    PresetAgentSession,
    _write_private_text,
    print_preset_progress,
)
from dstack._internal.cli.utils.common import console


class _FileLineReader:
    """`readline()` over a growing file, so stream parsing survives CLI
    restarts: offsets persist, and a later attach continues exactly where the
    previous reader stopped."""

    _POLL_SECONDS = 0.2
    _MAX_CHUNK = 1024 * 1024

    def __init__(
        self,
        path: Path,
        *,
        offset_store: "_OffsetStore",
        offset_key: str,
        is_alive: Callable[[], bool],
    ) -> None:
        self._path = path
        self._offset_store = offset_store
        self._offset_key = offset_key
        self._is_alive = is_alive
        self._offset = offset_store.get(offset_key)
        self._buffer = b""
        self._drained = False

    def _read_chunk(self) -> bytes:
        try:
            with self._path.open("rb") as f:
                f.seek(self._offset)
                return f.read(self._MAX_CHUNK)
        except OSError:
            return b""

    async def readline(self) -> bytes:
        while True:
            if b"\n" in self._buffer:
                line, self._buffer = self._buffer.split(b"\n", 1)
                return line + b"\n"
            # File IO runs off the event loop so a hung filesystem cannot
            # freeze the CLI.
            chunk = await asyncio.to_thread(self._read_chunk)
            if chunk:
                self._buffer += chunk
                self._offset += len(chunk)
                await asyncio.to_thread(self._offset_store.set, self._offset_key, self._offset)
                continue
            if not self._is_alive():
                if self._drained:
                    # A final partial line without a newline, then EOF.
                    line, self._buffer = self._buffer, b""
                    return line
                # One more read after death to catch the last flush.
                self._drained = True
                continue
            await asyncio.sleep(self._POLL_SECONDS)


class _OffsetStore:
    """Persists tailer/mirror byte offsets so resumed sessions do not repeat
    output. One instance serves the whole session — every reader and mirror
    shares it with disjoint keys, and the exclusive session claim guarantees no
    other process writes the file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        # Consumers flush from worker threads; serialize the update + write.
        self._lock = threading.Lock()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        self._data: dict[str, Any] = data if isinstance(data, dict) else {}

    def get(self, key: str) -> int:
        value = self._data.get(key, 0)
        return value if isinstance(value, int) and value >= 0 else 0

    def set(self, key: str, value: int) -> None:
        with self._lock:
            self._data[key] = value
            with suppress(OSError):
                _write_private_text(self._path, json.dumps(self._data) + "\n")


def open_session_offsets(session: PresetAgentSession) -> _OffsetStore:
    """The session's single offset store, shared by all its tailers."""
    return _OffsetStore(session.path / ".offsets.json")


class _ProgressTailer:
    def __init__(
        self,
        *,
        path: Path,
        redacted_values: Sequence[str],
        agent_session: PresetAgentSession,
        offset_store: Optional[_OffsetStore] = None,
        offset_key: str = "progress",
    ) -> None:
        self._path = path
        self._redacted_values = redacted_values
        self._agent_session = agent_session
        self._offset_store = offset_store
        self._offset_key = offset_key
        self._offset = offset_store.get(offset_key) if offset_store else 0

    async def run(self) -> None:
        while True:
            # File IO runs off the event loop; see _FileLineReader.readline.
            await asyncio.to_thread(self.flush)
            await asyncio.sleep(1)

    def flush(self) -> None:
        if not self._path.exists():
            return
        with self._path.open("r", encoding="utf-8", errors="replace") as f:
            f.seek(self._offset)
            lines = f.readlines()
            self._offset = f.tell()
        if lines and self._offset_store is not None:
            self._offset_store.set(self._offset_key, self._offset)
        for line in lines:
            message = _parse_progress(line)
            if message is not None:
                print_preset_progress(
                    redact(message, self._redacted_values),
                    agent_session=self._agent_session,
                )


class _RecordMirror:
    """Mirrors a workspace record file into the persistent session directory, redacted."""

    def __init__(
        self,
        *,
        source: Path,
        target: Path,
        redacted_values: Sequence[str],
        offset_store: Optional[_OffsetStore] = None,
        offset_key: str = "",
        echo: bool = True,
    ) -> None:
        self._source = source
        self._target = target
        self._redacted_values = redacted_values
        self._offset_store = offset_store
        self._offset_key = offset_key
        self._offset = offset_store.get(offset_key) if offset_store and offset_key else 0
        self._enabled = True
        self._echo = echo

    async def run(self) -> None:
        while True:
            # File IO runs off the event loop; see _FileLineReader.readline.
            await asyncio.to_thread(self.flush)
            await asyncio.sleep(1)

    def flush(self) -> None:
        if not self._enabled or not self._source.exists():
            return
        with self._source.open("rb") as f:
            f.seek(self._offset)
            data = f.read()
        # Mirror complete lines only; a partial line is kept for the next flush.
        end = data.rfind(b"\n")
        if end < 0:
            return
        chunk = data[: end + 1].decode("utf-8", errors="replace")
        self._offset += end + 1
        if self._offset_store is not None and self._offset_key:
            self._offset_store.set(self._offset_key, self._offset)
        try:
            if not self._target.exists():
                _write_private_text(self._target, "")
            # newline="" writes the binary-read chunk verbatim. Without it, text mode
            # re-translates "\n" to "\r\n" on Windows, doubling the "\r\n" a text-written
            # source already carries ("\r\r\n"), which reads back as a blank extra line.
            with self._target.open("a", encoding="utf-8", newline="") as f:
                f.write(redact(chunk, self._redacted_values))
                f.flush()
        except OSError as e:
            self._enabled = False
            if self._echo:
                console.print(f"[warning]Could not mirror {self._target.name}: {e}[/]")


def _parse_progress(line: str) -> Optional[str]:
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return line.strip() or None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict) and isinstance(value.get("message"), str):
        return value["message"].strip() or None
    return None
