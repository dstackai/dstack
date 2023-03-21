import os
from typing import Callable, Dict, Iterator, List, Optional

from azure.core.credentials import TokenCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobProperties, BlobServiceClient, ContainerClient, ContentSettings

from dstack.backend.base.storage import CloudStorage
from dstack.core.storage import StorageFile
from dstack.utils.common import removeprefix


class AzureStorage(CloudStorage):
    def __init__(
        self,
        account_url: str,
        credential: TokenCredential,
        container_name: str,
    ):
        self._blob_service_client = BlobServiceClient(
            account_url=account_url, credential=credential
        )
        self._container_client: ContainerClient = self._blob_service_client.get_container_client(
            container=container_name
        )
        self._container_name = container_name

    def upload_file(self, source_path: str, dest_path: str, callback: Callable[[int], None]):
        with open(source_path, "rb") as f:
            self._container_client.upload_blob(dest_path, f, overwrite=True)
        callback(os.path.getsize(source_path))

    def download_file(self, source_path: str, dest_path: str, callback: Callable[[int], None]):
        downloader = self._container_client.download_blob(source_path)
        with open(dest_path, "wb+") as f:
            downloader.readinto(f)
        callback(os.path.getsize(dest_path))

    def list_files(self, dirpath: str) -> List[StorageFile]:
        prefix = dirpath
        blobs: Iterator[BlobProperties] = self._container_client.list_blobs(
            name_starts_with=prefix
        )
        files = []
        for blob in blobs:
            file = StorageFile(
                filepath=removeprefix(blob.name, prefix),
                filesize_in_bytes=blob.size,
            )
            files.append(file)
        return files

    def list_objects(self, keys_prefix: str) -> List[str]:
        blobs_list = self._container_client.list_blobs(name_starts_with=keys_prefix)
        object_names = [blob.name for blob in blobs_list]
        return object_names

    def delete_object(self, key: str):
        try:
            self._container_client.delete_blob(key)
        except ResourceNotFoundError:
            pass

    def get_object(self, key: str) -> Optional[str]:
        blob_client = self._container_client.get_blob_client(key)
        try:
            return blob_client.download_blob().read()
        except ResourceNotFoundError:
            return None

    def put_object(self, key: str, content: str, metadata: Optional[Dict] = None):
        blob_client = self._container_client.get_blob_client(key)
        blob_client.upload_blob(
            data=content.encode(),
            content_settings=ContentSettings(content_type="text/plain", content_encoding="utf-8"),
            overwrite=True,
            metadata=metadata,
        )

    def get_signed_download_url(self, key: str) -> str:
        raise NotImplementedError

    def get_signed_upload_url(self, key: str) -> str:
        raise NotImplementedError
