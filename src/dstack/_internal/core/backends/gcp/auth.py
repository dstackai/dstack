import json

import google.auth
from google.auth.credentials import Credentials
from google.auth.exceptions import DefaultCredentialsError
from google.oauth2 import service_account

from dstack._internal.core.errors import BackendAuthError
from dstack._internal.core.models.backends.gcp import AnyGCPCreds, GCPServiceAccountCreds


def authenticate(creds: AnyGCPCreds) -> Credentials:
    if isinstance(creds, GCPServiceAccountCreds):
        return service_account.Credentials.from_service_account_info(json.loads(creds.data))

    try:
        default_credentials, _ = google.auth.default()
    except DefaultCredentialsError:
        raise BackendAuthError()

    return default_credentials
