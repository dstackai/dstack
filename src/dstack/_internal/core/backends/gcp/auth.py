import json
from typing import Optional, Tuple

import google.auth
from google.auth.credentials import Credentials
from google.auth.exceptions import DefaultCredentialsError
from google.oauth2 import service_account

from dstack._internal.core.errors import BackendAuthError
from dstack._internal.core.models.backends.gcp import AnyGCPCreds, GCPServiceAccountCreds


def authenticate(creds: AnyGCPCreds) -> Tuple[Credentials, Optional[str]]:
    """
    :raises BackendAuthError:
    :return: GCP credentials and project_id
    """
    if isinstance(creds, GCPServiceAccountCreds):
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
