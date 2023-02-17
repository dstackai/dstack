import re
from typing import Optional

from azure.core.credentials import TokenCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.keyvault.secrets import SecretClient

from dstack.backend.base.secrets import SecretsManager
from dstack.core.repo import RepoAddress
from dstack.core.secret import Secret


class AzureSecretsManager(SecretsManager):
    def __init__(self, credential: TokenCredential, vault_url: str):
        self.secrets_client = SecretClient(vault_url=vault_url, credential=credential)

    def get_secret(self, repo_address: RepoAddress, secret_name: str) -> Optional[Secret]:
        raise NotImplementedError(repo_address, secret_name)

    def add_secret(self, repo_address: RepoAddress, secret: Secret):
        raise NotImplementedError(repo_address, secret)

    def update_secret(self, repo_address: RepoAddress, secret: Secret):
        raise NotImplementedError(repo_address, secret)

    def delete_secret(self, repo_address: RepoAddress, secret_name: str):
        raise NotImplementedError(repo_address, secret_name)

    def get_credentials(self, repo_address: RepoAddress) -> Optional[str]:
        return self._get_secret_value(_get_credentials_key(repo_address))

    def add_credentials(self, repo_address: RepoAddress, data: str):
        credentials_key = _get_credentials_key(repo_address)
        self._set_secret_value(credentials_key, data)

    def update_credentials(self, repo_address: RepoAddress, data: str):
        raise NotImplementedError(repo_address, data)

    def _get_secret_value(self, secret_key: str) -> Optional[str]:
        try:
            secret = self.secrets_client.get_secret(secret_key)
        except ResourceNotFoundError:
            return
        return secret.value

    def _set_secret_value(self, secret_key: str, value: str):
        self.secrets_client.set_secret(secret_key, value)


# Azure allows only that characters set (by https://learn.microsoft.com/en-us/rest/api/keyvault/secrets/set-secret/set-secret?tabs=HTTP#uri-parameters ).
key_pattern = re.compile(r"([0-9a-zA-Z-]+)")


def _encode(key: str) -> str:
    """
    Punycode would be great choice to keep full original characters from the key in output ascii string.
    But it includes full range of ascii, which is more than the restriction. The procedure is substitute only forbidden
    ascii characters with "-". All other characters are handled by punycode.
    """
    result = []
    is_out_of_range = True
    for chunk in key_pattern.split(key):
        if is_out_of_range:
            for c in chunk:
                if ord(c) < 128:
                    result.append("-")
                else:
                    result.append(c)
        else:
            result.append(chunk)
        is_out_of_range = not is_out_of_range

    return "".join(result).encode("punycode").decode("ascii")


def _get_secret_key(repo_address: RepoAddress, secret_name: str) -> str:
    key = f"dstack-secrets-{repo_address.path(delimiter='-')}-{secret_name}"
    return _encode(key)


def _get_credentials_key(repo_address: RepoAddress) -> str:
    key = f"dstack-credentials-{repo_address.path(delimiter='-')}"
    return _encode(key)
