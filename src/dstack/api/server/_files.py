from typing import BinaryIO

from dstack._internal.core.models.common import validate_extra_ignore
from dstack._internal.core.models.files import FileArchive
from dstack._internal.server.schemas.files import GetFileArchiveByHashRequest
from dstack.api.server._group import APIClientGroup


class FilesAPIClient(APIClientGroup):
    def get_archive_by_hash(self, hash: str) -> FileArchive:
        body = GetFileArchiveByHashRequest(hash=hash)
        resp = self._request("/api/files/get_archive_by_hash", body=body.model_dump_json())
        return validate_extra_ignore(FileArchive, resp.json())

    def upload_archive(self, hash: str, fp: BinaryIO) -> FileArchive:
        resp = self._request("/api/files/upload_archive", files={"file": (hash, fp)})
        return validate_extra_ignore(FileArchive, resp.json())
