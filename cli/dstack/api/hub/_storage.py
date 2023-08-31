import os
from typing import Callable

import requests

from dstack.api.hub._api_client import HubAPIClient


class HUBStorage:
    def __init__(self, _client: HubAPIClient):
        self._client = _client

    def upload_file(
        self, backend: str, source_path: str, dest_path: str, callback: Callable[[int], None]
    ):
        url = self._client.upload_file(backend=backend, dest_path=dest_path)
        if not (url is None):
            with open(source_path, "rb") as f:
                headers = {}
                # Azure requires special headers
                if "blob.core.windows.net" in url:
                    headers["x-ms-blob-type"] = "BlockBlob"
                # AWS: requests.put() produces bad headers from empty file descriptor
                data = f if os.stat(source_path).st_size > 0 else None
                resp = requests.put(url, data=data, headers=headers)
                if resp.ok:
                    file_stat = os.stat(source_path)
                    callback(file_stat.st_size)

    def download_file(
        self, backend: str, source_path: str, dest_path: str, callback: Callable[[int], None]
    ):
        url = self._client.download_file(backend=backend, dest_path=source_path)
        if not (url is None):
            resp = requests.get(url)
            if resp.ok:
                with open(dest_path, "wb") as f:
                    f.write(resp.content)
                content_length = resp.headers.get("content-length", None)
                if not (content_length is None) and content_length.isdigit():
                    callback(int(content_length))
