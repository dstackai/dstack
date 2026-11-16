"""Incremental SSE event framing, independent of HTTP read/chunk boundaries."""

import codecs

from dstack._internal.proxy.lib.services.usage import MAX_SSE_EVENT_BYTES


class SSEDecoder:
    def __init__(self, max_event_bytes: int = MAX_SSE_EVENT_BYTES):
        self.max_event_bytes = max_event_bytes
        self._utf8 = codecs.getincrementaldecoder("utf-8")()
        self._line: list[str] = []
        self._data: list[str] = []
        self._size = 0
        self._after_cr = False

    def feed(self, data: bytes) -> list[str]:
        events = []
        for char in self._utf8.decode(data):
            if self._after_cr:
                self._after_cr = False
                if char == "\n":
                    continue
            self._size += len(char.encode("utf-8"))
            if self._size > self.max_event_bytes:
                raise ValueError("SSE event exceeds size limit")
            if char in ("\r", "\n"):
                line = "".join(self._line)
                self._line.clear()
                self._after_cr = char == "\r"
                if not line:
                    if self._data:
                        events.append("\n".join(self._data))
                    self._data.clear()
                    self._size = 0
                elif line == "data":
                    self._data.append("")
                elif line.startswith("data:"):
                    self._data.append(line[5:].removeprefix(" "))
            else:
                self._line.append(char)
        return events

    def finish(self) -> None:
        self._utf8.decode(b"", final=True)
        if self._line or self._data:
            raise ValueError("Truncated SSE event")
