from typing import Optional

from google.api_core import exceptions
from google.cloud import secretmanager
from google.oauth2 import service_account

from dstack.backend.base.secrets import SecretsManager
from dstack.core.secret import Secret


class GCPSecretsManager(SecretsManager):
    def __init__(
        self,
        project_id: str,
        bucket_name: str,
        credentials: Optional[service_account.Credentials],
    ):
        self.project_id = project_id
        self.bucket_name = bucket_name
        self.secrets_client = secretmanager.SecretManagerServiceClient(credentials=credentials)

    def get_secret(self, repo_id: str, secret_name: str) -> Optional[Secret]:
        secret_value = self._get_secret_value(
            _get_secret_key(self.bucket_name, repo_id, secret_name)
        )
        if secret_value is None:
            return None
        return Secret(secret_name=secret_name, secret_value=secret_value)

    def add_secret(self, repo_id: str, secret: Secret):
        secret_key = _get_secret_key(self.bucket_name, repo_id, secret.secret_name)
        self._create_secret(secret_key)
        self._add_secret_version(
            secret_key=secret_key,
            secret_value=secret.secret_value,
        )

    def update_secret(self, repo_id: str, secret: Secret):
        self._add_secret_version(
            secret_key=_get_secret_key(self.bucket_name, repo_id, secret.secret_name),
            secret_value=secret.secret_value,
        )

    def delete_secret(self, repo_id: str, secret_name: str):
        secret_resource = _get_secret_resource(
            self.project_id, _get_secret_key(self.bucket_name, repo_id, secret_name)
        )
        self.secrets_client.delete_secret(request={"name": secret_resource})

    def get_credentials(self, repo_id: str) -> Optional[str]:
        return self._get_secret_value(_get_credentials_key(self.bucket_name, repo_id))

    def add_credentials(self, repo_id: str, data: str):
        credentails_key = _get_credentials_key(self.bucket_name, repo_id)
        self._create_secret(credentails_key)
        self._add_secret_version(
            secret_key=credentails_key,
            secret_value=data,
        )

    def update_credentials(self, repo_id: str, data: str):
        self._add_secret_version(
            secret_key=_get_credentials_key(self.bucket_name, repo_id),
            secret_value=data,
        )

    def _get_secret_value(self, secret_key: str) -> Optional[str]:
        secret_version_resource = _get_secret_version_resource(self.project_id, secret_key)
        try:
            response = self.secrets_client.access_secret_version(name=secret_version_resource)
        except exceptions.NotFound:
            return None
        return response.payload.data.decode()

    def _create_secret(self, secret_key: str):
        try:
            self.secrets_client.create_secret(
                parent=_get_project_resource(self.project_id),
                secret_id=secret_key,
                secret={"replication": {"automatic": {}}},
            )
        except exceptions.AlreadyExists:
            pass

    def _add_secret_version(self, secret_key: str, secret_value: str):
        self.secrets_client.add_secret_version(
            parent=_get_secret_resource(self.project_id, secret_key),
            payload={"data": secret_value.encode()},
        )


def _get_project_resource(project_id: str) -> str:
    return f"projects/{project_id}"


def _get_secret_resource(project_id: str, secret_key: str) -> str:
    return f"{_get_project_resource(project_id)}/secrets/{secret_key}"


def _get_secret_version_resource(project_id: str, secret_key: str) -> str:
    secret_resource = _get_secret_resource(project_id, secret_key)
    return f"{secret_resource}/versions/latest"


def _get_secret_key(bucket_name: str, repo_id: str, secret_name: str) -> str:
    key = f"dstack-secrets-{bucket_name}-{repo_id}-{secret_name}"
    key = key.replace(".", "-")
    return key


def _get_credentials_key(bucket_name: str, repo_id: str) -> str:
    key = f"dstack-credentials-{bucket_name}-{repo_id}"
    key = key.replace(".", "-")
    return key
