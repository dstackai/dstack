import boto3.session
import botocore.exceptions
from boto3.session import Session

from dstack._internal.core.errors import BackendAuthError
from dstack._internal.core.models.backends.aws import AnyAWSCreds, AWSAccessKeyCreds
from dstack._internal.core.models.common import is_core_model_instance


def authenticate(creds: AnyAWSCreds, region: str) -> Session:
    session = get_session(creds=creds, region=region)
    validate_credentials(session)
    return session


def get_session(creds: AnyAWSCreds, region: str) -> Session:
    if is_core_model_instance(creds, AWSAccessKeyCreds):
        return boto3.session.Session(
            region_name=region,
            aws_access_key_id=creds.access_key,
            aws_secret_access_key=creds.secret_key,
        )
    return boto3.session.Session(region_name=region)


def validate_credentials(session: Session):
    sts = session.client("sts")
    try:
        sts.get_caller_identity()
    except (botocore.exceptions.ClientError, botocore.exceptions.NoCredentialsError):
        raise BackendAuthError()


def default_creds_available() -> bool:
    session = boto3.session.Session()
    try:
        validate_credentials(session)
    except BackendAuthError:
        return False
    return True
