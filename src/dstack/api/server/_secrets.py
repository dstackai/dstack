from typing import List

from pydantic import parse_obj_as

from dstack._internal.core.models.secrets import Secret
from dstack._internal.server.schemas.secrets import (
    CreateOrUpdateSecretRequest,
    DeleteSecretsRequest,
    GetSecretRequest,
)
from dstack.api.server._group import APIClientGroup


class SecretsAPIClient(APIClientGroup):
    def list(self, project_name: str) -> List[Secret]:
        resp = self._request(f"/api/project/{project_name}/secrets/list")
        return parse_obj_as(List[Secret.__response__], resp.json())

    def get(self, project_name: str, name: str) -> Secret:
        body = GetSecretRequest(name=name)
        resp = self._request(f"/api/project/{project_name}/secrets/get", body=body.json())
        return parse_obj_as(Secret, resp.json())

    def create_or_update(self, project_name: str, name: str, value: str) -> Secret:
        body = CreateOrUpdateSecretRequest(
            name=name,
            value=value,
        )
        resp = self._request(
            f"/api/project/{project_name}/secrets/create_or_update", body=body.json()
        )
        return parse_obj_as(Secret.__response__, resp.json())

    def delete(self, project_name: str, names: List[str]):
        body = DeleteSecretsRequest(secrets_names=names)
        self._request(f"/api/project/{project_name}/secrets/delete", body=body.json())
