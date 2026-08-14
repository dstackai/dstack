from typing import List

from dstack._internal.core.models.common import validate_extra_ignore
from dstack._internal.core.models.imports import Import
from dstack._internal.server.schemas.imports import DeleteImportRequest
from dstack.api.server._group import APIClientGroup


class ImportsAPIClient(APIClientGroup):
    def list(self, project_name: str) -> List[Import]:
        resp = self._request(f"/api/project/{project_name}/imports/list")
        return validate_extra_ignore(List[Import], resp.json())

    def delete(self, *, project_name: str, export_project_name: str, export_name: str) -> None:
        body = DeleteImportRequest(
            export_project_name=export_project_name, export_name=export_name
        )
        self._request(f"/api/project/{project_name}/imports/delete", body=body.model_dump_json())
