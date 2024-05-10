from typing import List, Optional

from pydantic import parse_obj_as

from dstack._internal.core.models.pools import Instance
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.runs import (
    PoolInstanceOffers,
    Requirements,
    Run,
    RunPlan,
    RunSpec,
)
from dstack._internal.server.schemas.runs import (
    CreateInstanceRequest,
    DeleteRunsRequest,
    GetOffersRequest,
    GetRunPlanRequest,
    GetRunRequest,
    ListRunsRequest,
    StopRunsRequest,
    SubmitRunRequest,
)
from dstack.api.server._group import APIClientGroup


class RunsAPIClient(APIClientGroup):
    def list(self, project_name: Optional[str], repo_id: Optional[str]) -> List[Run]:
        body = ListRunsRequest(project_name=project_name, repo_id=repo_id)
        resp = self._request("/api/runs/list", body=body.json())
        return parse_obj_as(List[Run.__response__], resp.json())

    def get(self, project_name: str, run_name: str) -> Run:
        body = GetRunRequest(run_name=run_name)
        resp = self._request(f"/api/project/{project_name}/runs/get", body=body.json())
        return parse_obj_as(Run.__response__, resp.json())

    def get_plan(self, project_name: str, run_spec: RunSpec) -> RunPlan:
        body = GetRunPlanRequest(run_spec=run_spec)
        resp = self._request(f"/api/project/{project_name}/runs/get_plan", body=body.json())
        return parse_obj_as(RunPlan.__response__, resp.json())

    def submit(self, project_name: str, run_spec: RunSpec) -> Run:
        body = SubmitRunRequest(run_spec=run_spec)
        resp = self._request(f"/api/project/{project_name}/runs/submit", body=body.json())
        return parse_obj_as(Run.__response__, resp.json())

    def stop(self, project_name: str, runs_names: List[str], abort: bool):
        body = StopRunsRequest(runs_names=runs_names, abort=abort)
        self._request(f"/api/project/{project_name}/runs/stop", body=body.json())

    def delete(self, project_name: str, runs_names: List[str]):
        body = DeleteRunsRequest(runs_names=runs_names)
        self._request(f"/api/project/{project_name}/runs/delete", body=body.json())

    # FIXME: get_offers and create_instance do not belong runs api

    def get_offers(
        self, project_name: str, profile: Profile, requirements: Requirements
    ) -> PoolInstanceOffers:
        body = GetOffersRequest(profile=profile, requirements=requirements)
        resp = self._request(f"/api/project/{project_name}/runs/get_offers", body=body.json())
        return parse_obj_as(PoolInstanceOffers.__response__, resp.json())

    def create_instance(
        self,
        project_name: str,
        profile: Profile,
        requirements: Requirements,
    ) -> Instance:
        body = CreateInstanceRequest(profile=profile, requirements=requirements)
        resp = self._request(f"/api/project/{project_name}/runs/create_instance", body=body.json())
        return parse_obj_as(Instance.__response__, resp.json())
