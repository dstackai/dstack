import json
from typing import Optional, Tuple

import google.auth
from google.auth.credentials import Credentials
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import storage
from google.oauth2 import service_account

from dstack._internal.core.errors import BackendAuthError
from dstack._internal.core.models.backends.gcp import (
    AnyGCPCreds,
    GCPDefaultCreds,
    GCPServiceAccountCreds,
)
from dstack._internal.core.models.common import is_core_model_instance


def authenticate(creds: AnyGCPCreds) -> Tuple[Credentials, Optional[str]]:
    """
    :raises BackendAuthError:
    :return: GCP credentials and project_id
    """
    credentials, project_id = get_credentials(creds)
    validate_credentials(credentials)
    return credentials, project_id


def get_credentials(creds: AnyGCPCreds) -> Tuple[Credentials, Optional[str]]:
    if is_core_model_instance(creds, GCPServiceAccountCreds):
        try:
            service_account_info = json.loads(creds.data)
            credentials = service_account.Credentials.from_service_account_info(
                service_account_info
            )
        except Exception:
            raise BackendAuthError()
        return credentials, credentials.project_id

    try:
        default_credentials, project_id = google.auth.default()
    except DefaultCredentialsError:
        raise BackendAuthError()

    return default_credentials, project_id


def validate_credentials(credentials: Credentials):
    try:
        storage_client = storage.Client(credentials=credentials)
        storage_client.list_buckets(max_results=1)
    except Exception:
        raise BackendAuthError()


def default_creds_available() -> bool:
    try:
        authenticate(GCPDefaultCreds())
    except BackendAuthError:
        return False
    return True
