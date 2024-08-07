from typing import Optional

from dstack._internal.server import settings

BOTO_AVAILABLE = True
try:
    import botocore.exceptions
    from boto3 import Session
except ImportError:
    BOTO_AVAILABLE = False


class S3Storage:
    def __init__(
        self,
        bucket: str,
        region: str,
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
            Key=_get_code_key(project_id, repo_id, code_hash),
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
                Key=_get_code_key(project_id, repo_id, code_hash),
            )
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise e
        return response["Body"].read()


def _get_code_key(project_id: str, repo_id: str, code_hash: str) -> str:
    return f"data/projects/{project_id}/codes/{repo_id}/{code_hash}"


_default_storage = None


def init_default_storage():
    global _default_storage
    if settings.SERVER_BUCKET is None:
        raise ValueError("settings.SERVER_BUCKET not set")
    if not BOTO_AVAILABLE:
        raise ValueError("AWS dependencies are not installed")
    _default_storage = S3Storage(
        bucket=settings.SERVER_BUCKET,
        region=settings.SERVER_BUCKET_REGION,
    )


def get_default_storage() -> Optional[S3Storage]:
    return _default_storage
