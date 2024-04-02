from typing import List

from pydantic import parse_obj_as

from dstack._internal.core.models.secrets import Secret
from dstack._internal.server.schemas.secrets import (
    AddSecretRequest,
    DeleteSecretsRequest,
    GetSecretsRequest,
    ListSecretsRequest,
)
from dstack.api.server._group import APIClientGroup


class SecretsAPIClient(APIClientGroup):
    def list(self, project_name: str, repo_id: str) -> List[Secret]:
        body = ListSecretsRequest(repo_id=repo_id)
        resp = self._request(f"/api/project/{project_name}/secrets/list", body=body.json())
        return parse_obj_as(List[Secret.__response__], resp.json())

    def get(self, project_name: str, repo_id: str, secret_name: str) -> Secret:
        raise NotImplementedError()
        body = GetSecretsRequest(repo_id=repo_id)
        resp = self._request(f"/api/project/{project_name}/secrets/get", body=body.json())
        return parse_obj_as(Secret, resp.json())

    def add(self, project_name: str, repo_id: str, secret_name: str, secret_value: str) -> Secret:
        body = AddSecretRequest(
            repo_id=repo_id, secret=Secret(name=secret_name, value=secret_value)
        )
        resp = self._request(f"/api/project/{project_name}/secrets/add", body=body.json())
        return parse_obj_as(Secret.__response__, resp.json())

    def delete(self, project_name: str, repo_id: str, secrets_names: List[str]):
        body = DeleteSecretsRequest(repo_id=repo_id, secrets_names=secrets_names)
        self._request(f"/api/project/{project_name}/secrets/delete", body=body.json())
