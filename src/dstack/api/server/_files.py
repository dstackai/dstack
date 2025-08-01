from typing import BinaryIO

from pydantic import parse_obj_as

from dstack._internal.core.models.files import FileArchive
from dstack._internal.server.schemas.files import GetFileArchiveByHashRequest
from dstack.api.server._group import APIClientGroup


class FilesAPIClient(APIClientGroup):
    def get_archive_by_hash(self, hash: str) -> FileArchive:
        body = GetFileArchiveByHashRequest(hash=hash)
        resp = self._request("/api/files/get_archive_by_hash", body=body.json())
        return parse_obj_as(FileArchive.__response__, resp.json())

    def upload_archive(self, hash: str, fp: BinaryIO) -> FileArchive:
        resp = self._request("/api/files/upload_archive", files={"file": (hash, fp)})
        return parse_obj_as(FileArchive.__response__, resp.json())
