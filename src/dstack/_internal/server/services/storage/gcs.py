from typing import Optional

from dstack._internal.server.services.storage.base import BaseStorage

GCS_AVAILABLE = True
try:
    from google.cloud import storage
    from google.cloud.exceptions import NotFound
except ImportError:
    GCS_AVAILABLE = False


class GCSStorage(BaseStorage):
    def __init__(
        self,
        bucket: str,
    ):
        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket)

    def upload_code(
        self,
        project_id: str,
        repo_id: str,
        code_hash: str,
        blob: bytes,
    ):
        blob_name = self._get_code_key(project_id, repo_id, code_hash)
        blob_obj = self._bucket.blob(blob_name)
        blob_obj.upload_from_string(blob)

    def get_code(
        self,
        project_id: str,
        repo_id: str,
        code_hash: str,
    ) -> Optional[bytes]:
        try:
            blob_name = self._get_code_key(project_id, repo_id, code_hash)
            blob = self._bucket.blob(blob_name)
        except NotFound:
            return None

        return blob.download_as_bytes()
