import base64
import json
from typing import Dict

import google.auth
import googleapiclient.discovery
import googleapiclient.errors
from google.auth.exceptions import DefaultCredentialsError
from google.oauth2 import service_account

from dstack._internal.backend.gcp import utils as gcp_utils
from dstack._internal.backend.gcp.config import GCPConfig
from dstack._internal.core.error import BackendAuthError, BackendError


class NotEnoughPermissionError(BackendError):
    pass


def authenticate(backend_config: GCPConfig):
    if backend_config.credentials["type"] == "service_account":
        return service_account.Credentials.from_service_account_info(
            json.loads(backend_config.credentials["data"])
        )
    try:
        default_credentials, _ = google.auth.default()
    except DefaultCredentialsError:
        raise BackendAuthError()
    service_account_email = backend_config.credentials["service_account_email"]
    iam_service = googleapiclient.discovery.build("iam", "v1", credentials=default_credentials)

    # We create a new key on each login and delete the old keys.
    # This will log out other Hub instances that have a project with the same bucket configured.
    # TODO: clarify if dstack supports multi-Hub setup.
    delete_service_account_keys(iam_service, backend_config.project_id, service_account_email)
    key = create_service_account_key(iam_service, backend_config.project_id, service_account_email)

    service_account_info = json.loads(base64.b64decode(key["privateKeyData"]))
    return service_account.Credentials.from_service_account_info(service_account_info)


def delete_service_account_keys(iam_service, project_id: str, service_account_email: str):
    service_account_resource = gcp_utils.get_service_account_resource(
        project_id, service_account_email
    )
    keys = (
        iam_service.projects()
        .serviceAccounts()
        .keys()
        .list(name=service_account_resource)
        .execute()
    )
    for key in keys["keys"]:
        if key["keyType"] == "USER_MANAGED":
            iam_service.projects().serviceAccounts().keys().delete(name=key["name"]).execute()


def create_service_account_key(iam_service, project_id: str, service_account_email: str) -> Dict:
    service_account_resource = gcp_utils.get_service_account_resource(
        project_id, service_account_email
    )
    try:
        key = (
            iam_service.projects()
            .serviceAccounts()
            .keys()
            .create(name=service_account_resource, body={})
            .execute()
        )
    except googleapiclient.errors.HttpError as e:
        if e.status_code == 403:
            raise NotEnoughPermissionError()
        raise e
    return key
