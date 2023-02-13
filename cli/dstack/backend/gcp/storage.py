from typing import Dict, List, Optional

from google.cloud import exceptions, storage

from dstack.backend.base.storage import Storage


class GCPStorage(Storage):
    def __init__(self, project_id: str, bucket_name: str):
        self.storage_client = self._get_client(project_id)
        self.bucket_name = bucket_name

    def configure(self):
        self.bucket = self._get_or_create_bucket(self.bucket_name)

    def put_object(self, key: str, content: str, metadata: Optional[Dict] = None):
        blob = self.bucket.blob(key)
        blob.upload_from_string(content)

    def get_object(self, key: str) -> Optional[str]:
        blob = self.bucket.get_blob(key)
        if blob is None:
            return None
        with blob.open() as f:
            return f.read()

    def delete_object(self, key: str):
        try:
            self.bucket.delete_blob(key)
        except exceptions.NotFound:
            pass

    def list_objects(self, keys_prefix: str) -> List[str]:
        # TODO pagination
        blobs = self.bucket.client.list_blobs(self.bucket.name, prefix=keys_prefix)
        object_names = [blob.name for blob in blobs]
        return object_names

    def _get_client(self, project_id: str) -> storage.Client:
        return storage.Client(project=project_id)

    def _get_or_create_bucket(self, bucket_name: str):
        try:
            return self.storage_client.create_bucket(bucket_name)
        except exceptions.Conflict:
            return self.storage_client.bucket(bucket_name)
