from typing import Tuple, Union

from azure.core.exceptions import ClientAuthenticationError
from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.mgmt.subscription import SubscriptionClient

from dstack._internal.core.backends.azure.models import (
    AnyAzureCreds,
    AzureClientCreds,
)
from dstack._internal.core.errors import BackendAuthError

AzureCredential = Union[ClientSecretCredential, DefaultAzureCredential]


def authenticate(creds: AnyAzureCreds) -> Tuple[AzureCredential, str]:
    credential, tenant_id = get_credential(creds)
    check_credential(credential)
    return credential, tenant_id


def get_credential(creds: AnyAzureCreds) -> Tuple[AzureCredential, str]:
    if isinstance(creds, AzureClientCreds):
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
