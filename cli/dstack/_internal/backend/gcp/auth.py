import base64
import json

import google.auth
import googleapiclient.discovery
from google.oauth2 import service_account

from dstack._internal.backend.gcp import utils as gcp_utils
from dstack._internal.backend.gcp.config import GCPConfig


def authenticate(backend_config: GCPConfig):
    if backend_config.credentials["type"] == "service_account":
        return service_account.Credentials.from_service_account_info(
            json.loads(backend_config.credentials["data"])
        )
    default_credentials, _ = google.auth.default()
    service_account_email = backend_config.credentials["service_account_email"]
    iam_service = googleapiclient.discovery.build("iam", "v1", credentials=default_credentials)
    service_account_resource = gcp_utils.get_service_account_resource(
        backend_config.project_id, service_account_email
    )
    # We create a new key on each login and delete the old keys.
    # This will log out other Hub instances that have a project with the same bucket configured.
    # TODO: clarify if dstack supports multi-Hub setup.
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
    key = (
        iam_service.projects()
        .serviceAccounts()
        .keys()
        .create(name=service_account_resource, body={})
        .execute()
    )
    service_account_info = json.loads(base64.b64decode(key["privateKeyData"]))
    return service_account.Credentials.from_service_account_info(service_account_info)
