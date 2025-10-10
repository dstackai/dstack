from typing import Optional

from dstack._internal.server.services.storage.base import BaseStorage

GCS_AVAILABLE = True
try:
    from google.cloud import storage
    from google.cloud.exceptions import NotFound
except ImportError:
    GCS_AVAILABLE = False
else:

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
            key = self._get_code_key(project_id, repo_id, code_hash)
            self._upload(key, blob)

        def get_code(
            self,
            project_id: str,
            repo_id: str,
            code_hash: str,
        ) -> Optional[bytes]:
            key = self._get_code_key(project_id, repo_id, code_hash)
            return self._get(key)

        def upload_archive(
            self,
            user_id: str,
            archive_hash: str,
            blob: bytes,
        ):
            key = self._get_archive_key(user_id, archive_hash)
            self._upload(key, blob)

        def get_archive(
            self,
            user_id: str,
            archive_hash: str,
        ) -> Optional[bytes]:
            key = self._get_archive_key(user_id, archive_hash)
            return self._get(key)

        def _upload(self, key: str, blob: bytes):
            blob_obj = self._bucket.blob(key)
            blob_obj.upload_from_string(blob)

        def _get(self, key: str) -> Optional[bytes]:
            try:
                blob = self._bucket.blob(key)
            except NotFound:
                return None
            return blob.download_as_bytes()
