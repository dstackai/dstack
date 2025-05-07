import json
from typing import Optional, Tuple

import google.api_core.exceptions
import google.auth
import google.cloud.compute_v1 as compute_v1
from google.auth.credentials import Credentials
from google.auth.exceptions import DefaultCredentialsError
from google.oauth2 import service_account

from dstack._internal.core.backends.gcp.models import (
    AnyGCPCreds,
    GCPServiceAccountCreds,
)
from dstack._internal.core.errors import BackendAuthError


def authenticate(creds: AnyGCPCreds, project_id: Optional[str] = None) -> Tuple[Credentials, str]:
    credentials, credentials_project_id = get_credentials(creds)
    if project_id is None:
        # If project_id is not specified explicitly, try using credentials' project_id.
        # Explicit project_id takes precedence because credentials' project_id may be irrelevant.
        # For example, with Workload Identity Federation for GKE, it's cluster project_id.
        project_id = credentials_project_id
    if project_id is None:
        raise BackendAuthError("Credentials require project_id to be specified")
    validate_credentials(credentials, project_id)
    return credentials, project_id


def get_credentials(creds: AnyGCPCreds) -> Tuple[Credentials, Optional[str]]:
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
        raise BackendAuthError("Failed to find default credentials")

    return default_credentials, project_id


def validate_credentials(credentials: Credentials, project_id: str):
    try:
        regions_client = compute_v1.RegionsClient(credentials=credentials)
        regions_client.list(project=project_id)
    except google.api_core.exceptions.NotFound:
        raise BackendAuthError(f"project_id {project_id} not found")
    except Exception:
        raise BackendAuthError("Insufficient permissions")
