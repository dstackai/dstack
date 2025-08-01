from typing import Optional

from dstack._internal.server import settings
from dstack._internal.server.services.storage.base import BaseStorage
from dstack._internal.server.services.storage.gcs import GCS_AVAILABLE, GCSStorage
from dstack._internal.server.services.storage.s3 import BOTO_AVAILABLE, S3Storage

_default_storage = None


def init_default_storage():
    global _default_storage
    if settings.SERVER_S3_BUCKET is None and settings.SERVER_GCS_BUCKET is None:
        raise ValueError(
            "Either settings.SERVER_S3_BUCKET or settings.SERVER_GCS_BUCKET must be set"
        )
    if settings.SERVER_S3_BUCKET and settings.SERVER_GCS_BUCKET:
        raise ValueError(
            "Only one of settings.SERVER_S3_BUCKET or settings.SERVER_GCS_BUCKET can be set"
        )

    if settings.SERVER_S3_BUCKET:
        if not BOTO_AVAILABLE:
            raise ValueError("AWS dependencies are not installed")
        _default_storage = S3Storage(
            bucket=settings.SERVER_S3_BUCKET,
            region=settings.SERVER_S3_BUCKET_REGION,
        )
    elif settings.SERVER_GCS_BUCKET:
        if not GCS_AVAILABLE:
            raise ValueError("GCS dependencies are not installed")
        _default_storage = GCSStorage(
            bucket=settings.SERVER_GCS_BUCKET,
        )


def get_default_storage() -> Optional[BaseStorage]:
    return _default_storage
