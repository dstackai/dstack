from typing import Optional

from dstack._internal.server.services.storage.base import BaseStorage

BOTO_AVAILABLE = True
try:
    import botocore.exceptions
    from boto3 import Session
except ImportError:
    BOTO_AVAILABLE = False


class S3Storage(BaseStorage):
    def __init__(
        self,
        bucket: str,
        region: Optional[str] = None,
    ):
        self._session = Session()
        self._client = self._session.client("s3", region_name=region)
        self.bucket = bucket

    def upload_code(
        self,
        project_id: str,
        repo_id: str,
        code_hash: str,
        blob: bytes,
    ):
        self._client.put_object(
            Bucket=self.bucket,
            Key=self._get_code_key(project_id, repo_id, code_hash),
            Body=blob,
        )

    def get_code(
        self,
        project_id: str,
        repo_id: str,
        code_hash: str,
    ) -> Optional[bytes]:
        try:
            response = self._client.get_object(
                Bucket=self.bucket,
                Key=self._get_code_key(project_id, repo_id, code_hash),
            )
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise e
        return response["Body"].read()
