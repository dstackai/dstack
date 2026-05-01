from typing import List

from pydantic import parse_obj_as

from dstack._internal.core.compatibility.exports import (
    get_create_export_excludes,
    get_update_export_excludes,
)
from dstack._internal.core.models.exports import Export
from dstack._internal.server.schemas.exports import (
    CreateExportRequest,
    DeleteExportRequest,
    UpdateExportRequest,
)
from dstack.api.server._group import APIClientGroup


class ExportsAPIClient(APIClientGroup):
    def list(self, project_name: str) -> List[Export]:
        resp = self._request(f"/api/project/{project_name}/exports/list")
        return parse_obj_as(List[Export.__response__], resp.json())

    def create(
        self,
        project_name: str,
        name: str,
        *,
        importer_projects: List[str] = [],
        exported_fleets: List[str] = [],
        exported_gateways: List[str] = [],
    ) -> Export:
        body = CreateExportRequest(
            name=name,
            importer_projects=importer_projects,
            exported_fleets=exported_fleets,
            exported_gateways=exported_gateways,
        )
        resp = self._request(
            f"/api/project/{project_name}/exports/create",
            body=body.json(exclude=get_create_export_excludes(body)),
        )
        return parse_obj_as(Export.__response__, resp.json())

    def update(
        self,
        project_name: str,
        name: str,
        *,
        add_importer_projects: List[str] = [],
        remove_importer_projects: List[str] = [],
        add_exported_fleets: List[str] = [],
        remove_exported_fleets: List[str] = [],
        add_exported_gateways: List[str] = [],
        remove_exported_gateways: List[str] = [],
    ) -> Export:
        body = UpdateExportRequest(
            name=name,
            add_importer_projects=add_importer_projects,
            remove_importer_projects=remove_importer_projects,
            add_exported_fleets=add_exported_fleets,
            remove_exported_fleets=remove_exported_fleets,
            add_exported_gateways=add_exported_gateways,
            remove_exported_gateways=remove_exported_gateways,
        )
        resp = self._request(
            f"/api/project/{project_name}/exports/update",
            body=body.json(exclude=get_update_export_excludes(body)),
        )
        return parse_obj_as(Export.__response__, resp.json())

    def delete(self, project_name: str, name: str) -> None:
        body = DeleteExportRequest(name=name)
        self._request(f"/api/project/{project_name}/exports/delete", body=body.json())
