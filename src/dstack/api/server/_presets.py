from typing import Iterator, Tuple

from dstack._internal.core.errors import ClientError
from dstack._internal.core.models.common import validate_extra_ignore
from dstack._internal.core.models.presets import PresetSpec
from dstack._internal.server.schemas.presets import (
    PRESET_FILES_CONTENT_LENGTH_BYTES,
    PRESET_FILES_PATH_LENGTH_BYTES,
    GetPresetFilesRequest,
    GetPresetRequest,
    GetPresetResponse,
    PushPresetRequest,
    PushPresetResponse,
)
from dstack.api.server._group import APIClientGroup

_STREAM_CHUNK_SIZE = 64 * 1024


class PresetsAPIClient(APIClientGroup):
    def push(self, project_name: str, name: str, spec: PresetSpec) -> PushPresetResponse:
        body = PushPresetRequest(name=name, spec=spec)
        resp = self._request(
            f"/api/project/{project_name}/presets/push", body=body.model_dump_json()
        )
        return validate_extra_ignore(PushPresetResponse, resp.json())

    def get(self, project_name: str, name_or_id: str) -> GetPresetResponse:
        body = GetPresetRequest(name_or_id=name_or_id)
        resp = self._request(
            f"/api/project/{project_name}/presets/get", body=body.model_dump_json()
        )
        return validate_extra_ignore(GetPresetResponse, resp.json())

    def get_files(self, project_name: str, name_or_id: str) -> Iterator[Tuple[str, bytes]]:
        """Yields `(path, archive)` for every file the preset carries, in one
        request. The response is consumed as it arrives, so the number of files
        does not change how much is held in memory."""
        body = GetPresetFilesRequest(name_or_id=name_or_id)
        resp = self._request(
            f"/api/project/{project_name}/presets/get_files",
            body=body.model_dump_json(),
            stream=True,
        )
        return _iter_archives(resp.iter_content(chunk_size=_STREAM_CHUNK_SIZE))


def _iter_archives(chunks: Iterator[bytes]) -> Iterator[Tuple[str, bytes]]:
    reader = _ChunkReader(chunks)
    while True:
        header = reader.read(PRESET_FILES_PATH_LENGTH_BYTES, allow_eof=True)
        if header is None:
            return
        path = reader.read(int.from_bytes(header, "big")).decode()
        size = int.from_bytes(reader.read(PRESET_FILES_CONTENT_LENGTH_BYTES), "big")
        yield path, reader.read(size)


class _ChunkReader:
    """Exact-size reads over a chunked response body."""

    def __init__(self, chunks: Iterator[bytes]):
        self._chunks = chunks
        self._buffer = bytearray()

    def read(self, size: int, allow_eof: bool = False):
        while len(self._buffer) < size:
            chunk = next(self._chunks, None)
            if chunk is None:
                if allow_eof and not self._buffer:
                    return None
                raise ClientError("Preset file stream ended early")
            self._buffer += chunk
        data = bytes(self._buffer[:size])
        del self._buffer[:size]
        return data
