from typing import Callable, Dict, List, Optional

import botocore.exceptions
from boto3.s3 import transfer
from botocore.client import BaseClient

from dstack._internal.backend.base.storage import (
    SIGNED_URL_EXPIRATION,
    CloudStorage,
    add_namespace,
    drop_namespace,
)
from dstack._internal.core.storage import StorageFile


class AWSStorage(CloudStorage):
    def __init__(self, s3_client: BaseClient, bucket_name: str, namespace: str):
        self.s3_client = s3_client
        self.bucket_name = bucket_name
        self.namespace = namespace

    def put_object(self, key: str, content: str, metadata: Optional[Dict] = None):
        key = add_namespace(self.namespace, key)
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=content,
            Metadata=metadata if metadata is not None else {},
        )

    def get_object(self, key: str) -> Optional[str]:
        key = add_namespace(self.namespace, key)
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise e
        return response["Body"].read().decode()

    def delete_object(self, key: str):
        key = add_namespace(self.namespace, key)
        self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)

    def list_objects(self, keys_prefix: str) -> List[str]:
        keys_prefix = add_namespace(self.namespace, keys_prefix)
        response = self.s3_client.list_objects_v2(Bucket=self.bucket_name, Prefix=keys_prefix)
        if response["KeyCount"] == 0:
            return []
        object_keys = []
        for obj_metadata in response["Contents"]:
            key = drop_namespace(self.namespace, obj_metadata["Key"])
            object_keys.append(key)
        return object_keys

    def list_files(self, prefix: str, recursive: bool) -> List[StorageFile]:
        prefix = add_namespace(self.namespace, prefix)
        paginator = self.s3_client.get_paginator("list_objects")
        delimiter = "/"
        if recursive:
            delimiter = ""
        page_iterator = paginator.paginate(
            Bucket=self.bucket_name, Prefix=prefix, Delimiter=delimiter
        )
        files = []
        for page in page_iterator:
            for obj in page.get("Contents") or []:
                if obj["Size"] > 0:
                    filepath = drop_namespace(self.namespace, obj["Key"])
                    files.append(
                        StorageFile(
                            filepath=filepath,
                            filesize_in_bytes=obj["Size"],
                        )
                    )
            for obj in page.get("CommonPrefixes") or []:
                filepath = drop_namespace(self.namespace, obj["Prefix"])
                files.append(
                    StorageFile(
                        filepath=filepath,
                    )
                )
        return files

    def download_file(self, source_path: str, dest_path: str, callback: Callable[[int], None]):
        source_path = add_namespace(self.namespace, source_path)
        downloader = transfer.S3Transfer(
            self.s3_client, transfer.TransferConfig(), transfer.OSUtils()
        )
        downloader.download_file(self.bucket_name, source_path, dest_path, callback=callback)

    def upload_file(self, source_path: str, dest_path: str, callback: Callable[[int], None]):
        dest_path = add_namespace(self.namespace, dest_path)
        uploader = transfer.S3Transfer(
            self.s3_client, transfer.TransferConfig(), transfer.OSUtils()
        )
        uploader.upload_file(source_path, self.bucket_name, dest_path, callback)

    def get_signed_download_url(self, key: str) -> str:
        key = add_namespace(self.namespace, key)
        url = self.s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket_name,
                "Key": key,
            },
            ExpiresIn=SIGNED_URL_EXPIRATION,
        )
        return url

    def get_signed_upload_url(self, key: str) -> str:
        key = add_namespace(self.namespace, key)
        url = self.s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.bucket_name,
                "Key": key,
            },
            ExpiresIn=SIGNED_URL_EXPIRATION,
        )
        return url
