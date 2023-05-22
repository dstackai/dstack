import os
from abc import ABC
from typing import Callable, Dict, List, Optional

import requests

from dstack.api.hub._api_client import HubAPIClient
from dstack.backend.base.storage import SIGNED_URL_EXPIRATION, CloudStorage
from dstack.core.storage import StorageFile


class HUBStorage(CloudStorage, ABC):
    def __init__(self, _client: HubAPIClient):
        self._client = _client

    def upload_file(self, source_path: str, dest_path: str, callback: Callable[[int], None]):
        url = self._client.upload_file(dest_path=dest_path)
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

    def download_file(self, source_path: str, dest_path: str, callback: Callable[[int], None]):
        url = self._client.download_file(dest_path=source_path)
        if not (url is None):
            resp = requests.get(url)
            if resp.ok:
                with open(dest_path, "wb") as f:
                    f.write(resp.content)
                content_length = resp.headers.get("content-length", None)
                if not (content_length is None) and content_length.isdigit():
                    callback(int(content_length))

    def put_object(self, key: str, content: str, metadata: Optional[Dict] = None):
        pass

    def get_object(self, key: str) -> Optional[str]:
        pass

    def delete_object(self, key: str):
        pass

    def list_objects(self, keys_prefix: str) -> List[str]:
        pass

    def list_files(self, dirpath: str) -> List[StorageFile]:
        pass

    def get_signed_download_url(self, key: str) -> str:
        pass

    def get_signed_upload_url(self, key: str) -> str:
        pass
