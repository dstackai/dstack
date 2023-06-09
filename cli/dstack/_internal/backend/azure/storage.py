import os
from datetime import timedelta
from typing import Callable, Dict, Iterator, List, Optional

from azure.core.credentials import TokenCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import (
    BlobProperties,
    BlobServiceClient,
    ContainerClient,
    ContentSettings,
    generate_blob_sas,
)

from dstack._internal.backend.azure.utils import (
    DSTACK_CONTAINER_NAME,
    get_blob_storage_account_url,
)
from dstack._internal.backend.base.storage import CloudStorage
from dstack._internal.core.storage import StorageFile
from dstack._internal.utils.common import get_current_datetime


class AzureStorage(CloudStorage):
    def __init__(
        self,
        credential: TokenCredential,
        storage_account: str,
    ):
        self.storage_account = storage_account
        self.storage_account_url = get_blob_storage_account_url(storage_account)
        self._blob_service_client = BlobServiceClient(
            credential=credential,
            account_url=self.storage_account_url,
        )
        self._container_client: ContainerClient = self._blob_service_client.get_container_client(
            container=DSTACK_CONTAINER_NAME
        )

    def upload_file(self, source_path: str, dest_path: str, callback: Callable[[int], None]):
        with open(source_path, "rb") as f:
            self._container_client.upload_blob(dest_path, f, overwrite=True)
        callback(os.path.getsize(source_path))

    def download_file(self, source_path: str, dest_path: str, callback: Callable[[int], None]):
        downloader = self._container_client.download_blob(source_path)
        with open(dest_path, "wb+") as f:
            downloader.readinto(f)
        callback(os.path.getsize(dest_path))

    def list_files(self, prefix: str, recursive: bool) -> List[StorageFile]:
        delimiter = "/"
        if recursive:
            delimiter = ""
        blobs: Iterator[BlobProperties] = self._container_client.walk_blobs(
            name_starts_with=prefix, delimiter=delimiter
        )
        files = []
        for blob in blobs:
            file = StorageFile(
                filepath=blob.name,
                filesize_in_bytes=blob.get("size"),
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
        user_delegation_key = self._blob_service_client.get_user_delegation_key(
            key_start_time=get_current_datetime(),
            key_expiry_time=get_current_datetime() + timedelta(hours=1),
        )
        sas = generate_blob_sas(
            account_name=self.storage_account,
            container_name=DSTACK_CONTAINER_NAME,
            blob_name=key,
            user_delegation_key=user_delegation_key,
            permission="r",
            expiry=get_current_datetime() + timedelta(hours=1),
        )
        url = self._build_signed_url(key, sas)
        return url

    def get_signed_upload_url(self, key: str) -> str:
        user_delegation_key = self._blob_service_client.get_user_delegation_key(
            key_start_time=get_current_datetime(),
            key_expiry_time=get_current_datetime() + timedelta(hours=1),
        )
        sas = generate_blob_sas(
            account_name=self.storage_account,
            container_name=DSTACK_CONTAINER_NAME,
            blob_name=key,
            user_delegation_key=user_delegation_key,
            permission="cw",
            expiry=get_current_datetime() + timedelta(hours=1),
        )
        url = self._build_signed_url(key, sas)
        return url

    def _build_signed_url(self, key: str, sas: str) -> str:
        return f"{self.storage_account_url}/{DSTACK_CONTAINER_NAME}/{key}?{sas}"
