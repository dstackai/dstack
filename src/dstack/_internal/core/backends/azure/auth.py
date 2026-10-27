from typing import Union

from azure.core.exceptions import ClientAuthenticationError
from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.mgmt.subscription import SubscriptionClient

from dstack._internal.core.backends.azure.models import (
    AnyAzureCreds,
    AzureClientCreds,
)
from dstack._internal.core.errors import BackendAuthError
from dstack._internal.utils.common import get_or_error

AzureCredential = Union[ClientSecretCredential, DefaultAzureCredential]


def authenticate(creds: AnyAzureCreds) -> AzureCredential:
    credential = get_credential(creds)
    check_credential(credential)
    return credential


def get_credential(creds: AnyAzureCreds) -> AzureCredential:
    if isinstance(creds, AzureClientCreds):
        return ClientSecretCredential(
            # The configurator populates `tenant_id` from the backend config if it's missing
            tenant_id=get_or_error(creds.tenant_id),
            client_id=creds.client_id,
            client_secret=creds.client_secret,
        )
    return DefaultAzureCredential()


def check_credential(credential: AzureCredential):
    client = SubscriptionClient(credential=credential)
    try:
        list(client.subscriptions.list())
    except ClientAuthenticationError:
        raise BackendAuthError()
