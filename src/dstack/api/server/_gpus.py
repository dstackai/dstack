from typing import List, Optional

from pydantic import parse_obj_as

from dstack._internal.core.models.runs import RunSpec
from dstack._internal.server.schemas.gpus import GetRunGpusRequest, RunGpusResponse
from dstack.api.server._group import APIClientGroup


class GpusAPIClient(APIClientGroup):
    def get_gpus(
        self,
        project_name: str,
        run_spec: RunSpec,
        group_by: Optional[List[str]] = None,
    ) -> RunGpusResponse:
        body = GetRunGpusRequest(run_spec=run_spec, group_by=group_by)
        resp = self._request(
            f"/api/project/{project_name}/gpus/list",
            body=body.json(),
        )
        return parse_obj_as(RunGpusResponse, resp.json())
