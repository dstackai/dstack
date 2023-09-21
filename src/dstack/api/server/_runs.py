from typing import List

from pydantic import parse_obj_as

from dstack._internal.core.models.runs import Run, RunPlan, RunSpec
from dstack._internal.server.schemas.runs import GetRunPlanRequest, GetRunRequest
from dstack.api.server._group import APIClientGroup


class RunsAPIClient(APIClientGroup):
    def list(self, project_name: str) -> List[Run]:
        resp = self._request(f"/api/project/{project_name}/runs/list")
        return parse_obj_as(List[Run], resp.json())

    def get(self, project_name: str, run_name: str) -> Run:
        body = GetRunRequest(run_name=run_name)
        resp = self._request(f"/api/project/{project_name}/runs/get", body=body.json())
        return parse_obj_as(Run, resp.json())

    def get_plan(self, project_name: str, run_spec: RunSpec) -> RunPlan:
        body = GetRunPlanRequest(run_spec=run_spec)
        resp = self._request(f"/api/project/{project_name}/runs/get_plan", body=body.json())
        return parse_obj_as(RunPlan, resp.json())

    def submit(self, project_name: str, run_spec: RunSpec) -> Run:
        body = GetRunPlanRequest(run_spec=run_spec)
        resp = self._request(f"/api/project/{project_name}/runs/submit", body=body.json())
        return parse_obj_as(Run, resp.json())

    def stop(self, project_name: str, run_name: str):
        raise NotImplemented()

    def delete(self, project_name: str, run_name: str):
        raise NotImplemented()
