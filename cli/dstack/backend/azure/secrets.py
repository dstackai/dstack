import base64
from typing import Optional

from azure.core.credentials import TokenCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.keyvault.secrets import SecretClient

from dstack.backend.base.secrets import SecretsManager
from dstack.core.secret import Secret


class AzureSecretsManager(SecretsManager):
    def __init__(self, vault_url: str, credential: TokenCredential):
        self.secrets_client = SecretClient(vault_url=vault_url, credential=credential)

    def get_secret(self, repo_id: str, secret_name: str) -> Optional[Secret]:
        secret_value = self._get_secret_value(_get_secret_key(repo_id, secret_name))
        if secret_value is None:
            return None
        return Secret(secret_name=secret_name, secret_value=secret_value)

    def add_secret(self, repo_id: str, secret: Secret):
        secret_key = _get_secret_key(repo_id, secret.secret_name)
        self._set_secret_value(secret_key, secret.secret_value)

    def update_secret(self, repo_id: str, secret: Secret):
        secret_key = _get_secret_key(repo_id, secret.secret_name)
        self._set_secret_value(secret_key, secret.secret_value)

    def delete_secret(self, repo_id: str, secret_name: str):
        secret_key = _get_secret_key(repo_id, secret_name)
        self.secrets_client.begin_delete_secret(secret_key).result()

    def get_credentials(self, repo_id: str) -> Optional[str]:
        return self._get_secret_value(_get_credentials_key(repo_id))

    def add_credentials(self, repo_id: str, data: str):
        self.update_credentials(repo_id, data)

    def update_credentials(self, repo_id: str, data: str):
        credentials_key = _get_credentials_key(repo_id)
        self._set_secret_value(credentials_key, data)

    def _get_secret_value(self, secret_key: str) -> Optional[str]:
        try:
            secret = self.secrets_client.get_secret(secret_key)
        except ResourceNotFoundError:
            return None
        return secret.value

    def _set_secret_value(self, secret_key: str, value: str):
        self.secrets_client.set_secret(secret_key, value)


def _get_secret_key(repo_id: str, secret_name: str) -> str:
    repo_part = repo_id
    return _encode_key(f"dstack-secrets-{repo_part}-", secret_name)


def _get_credentials_key(repo_id: str) -> str:
    repo_part = repo_id
    return f"dstack-credentials-{repo_part}"


def _encode_key(key_prefix: str, key_suffix: str) -> str:
    key_suffix = base64.b32encode(key_suffix.encode()).decode().replace("=", "-")
    return f"{key_prefix}{key_suffix}"
