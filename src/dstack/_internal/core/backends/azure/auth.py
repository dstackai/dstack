from typing import Tuple, Union

from azure.core.exceptions import ClientAuthenticationError
from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.mgmt.subscription import SubscriptionClient

from dstack._internal.core.errors import BackendAuthError
from dstack._internal.core.models.backends.azure import (
    AnyAzureCreds,
    AzureClientCreds,
    AzureDefaultCreds,
)
from dstack._internal.core.models.common import is_core_model_instance

AzureCredential = Union[ClientSecretCredential, DefaultAzureCredential]


def authenticate(creds: AnyAzureCreds) -> Tuple[AzureCredential, str]:
    credential, tenant_id = get_credential(creds)
    check_credential(credential)
    return credential, tenant_id


def get_credential(creds: AnyAzureCreds) -> Tuple[AzureCredential, str]:
    if is_core_model_instance(creds, AzureClientCreds):
        credential = ClientSecretCredential(
            tenant_id=creds.tenant_id,
            client_id=creds.client_id,
            client_secret=creds.client_secret,
        )
        return credential, creds.tenant_id

    return DefaultAzureCredential(), None


def check_credential(credential: AzureCredential):
    client = SubscriptionClient(credential=credential)
    try:
        list(client.subscriptions.list())
    except ClientAuthenticationError:
        raise BackendAuthError()


def default_creds_available() -> bool:
    try:
        authenticate(AzureDefaultCreds())
    except BackendAuthError:
        return False
    return True
