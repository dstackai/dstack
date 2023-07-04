import time
from typing import Any, List

import botocore.exceptions
from boto3 import Session
from botocore.client import BaseClient


def get_s3_client(session: Session, **kwargs) -> BaseClient:
    return _get_client(session, "s3", **kwargs)


def get_ec2_client(session: Session, **kwargs) -> BaseClient:
    return _get_client(session, "ec2", **kwargs)


def get_iam_client(session: Session, **kwargs) -> BaseClient:
    return _get_client(session, "iam", **kwargs)


def get_logs_client(session: Session, **kwargs) -> BaseClient:
    return _get_client(session, "logs", **kwargs)


def get_secretsmanager_client(session: Session, **kwargs) -> BaseClient:
    return _get_client(session, "secretsmanager", **kwargs)


def get_sts_client(session: Session, **kwargs) -> BaseClient:
    return _get_client(session, "sts", **kwargs)


def _get_client(session: Session, client_name: str, **kwargs) -> BaseClient:
    return session.client(client_name, **kwargs)


def retry_operation_on_service_errors(
    func, errors: List[str], max_retries: int = 3, delay: int = 1, *args, **kwargs
) -> Any:
    last_error = None
    for _ in range(max_retries):
        try:
            return func(*args, **kwargs)
        except botocore.exceptions.ClientError as e:
            last_error = e
            if e.response["Error"]["Code"] in errors:
                time.sleep(delay)
            else:
                raise e
    raise last_error
