from typing import List, Optional

import botocore.exceptions
from botocore.client import BaseClient

from dstack.backend.base.storage import Storage


class AWSStorage(Storage):
    def __init__(self, s3_client: BaseClient, bucket_name: str):
        self.s3_client = s3_client
        self.bucket_name = bucket_name

    def put_object(self, key: str, content: str):
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=content,
        )

    def get_object(self, key: str) -> Optional[str]:
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise e
        return response["Body"].read().decode()

    def delete_object(self, key: str):
        self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)

    def list_objects(self, keys_prefix: str) -> List[str]:
        response = self.s3_client.list_objects_v2(Bucket=self.bucket_name, Prefix=keys_prefix)
        if response["KeyCount"] == 0:
            return []
        object_keys = []
        for obj_metadata in response["Contents"]:
            object_keys.append(obj_metadata["Key"])
        return object_keys
