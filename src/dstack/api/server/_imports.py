from typing import List

from dstack._internal.core.models.common import validate_extra_ignore
from dstack._internal.core.models.imports import Import, ListImportsResponse
from dstack._internal.server.schemas.imports import DeleteImportRequest
from dstack._internal.utils.logging import get_logger
from dstack.api.server._group import APIClientGroup

logger = get_logger(__name__)


class ImportsAPIClient(APIClientGroup):
    def list_imports(self, project_name: str) -> ListImportsResponse:
        resp = self._request(f"/api/project/{project_name}/imports/list")
        if isinstance(resp.json(), list):
            return ListImportsResponse(
                imports=validate_extra_ignore(list[Import], resp.json()),
            )
        return validate_extra_ignore(ListImportsResponse, resp.json())

    def list(self, project_name: str) -> List[Import]:
        logger.warning("The list() method is deprecated in favor of list_imports().")
        resp = self._request(f"/api/project/{project_name}/imports/list")
        if isinstance(resp.json(), list):
            return validate_extra_ignore(List[Import], resp.json())
        return validate_extra_ignore(ListImportsResponse, resp.json()).imports

    def delete(self, *, project_name: str, export_project_name: str, export_name: str) -> None:
        body = DeleteImportRequest(
            export_project_name=export_project_name, export_name=export_name
        )
        self._request(f"/api/project/{project_name}/imports/delete", body=body.model_dump_json())
