from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from pydantic import parse_obj_as

from dstack._internal.core.models.runs import (
    ApplyRunPlanInput,
    Run,
    RunPlan,
    RunSpec,
)
from dstack._internal.server.schemas.runs import (
    ApplyRunPlanRequest,
    DeleteRunsRequest,
    GetRunPlanRequest,
    GetRunRequest,
    ListRunsRequest,
    StopRunsRequest,
)
from dstack.api.server._group import APIClientGroup


class RunsAPIClient(APIClientGroup):
    def list(
        self,
        project_name: Optional[str],
        repo_id: Optional[str],
        username: Optional[str] = None,
        only_active: bool = False,
        prev_submitted_at: Optional[datetime] = None,
        prev_run_id: Optional[UUID] = None,
        limit: int = 100,
        ascending: bool = False,
    ) -> List[Run]:
        body = ListRunsRequest(
            project_name=project_name,
            repo_id=repo_id,
            username=username,
            only_active=only_active,
            prev_submitted_at=prev_submitted_at,
            prev_run_id=prev_run_id,
            limit=limit,
            ascending=ascending,
        )
        resp = self._request("/api/runs/list", body=body.json())
        return parse_obj_as(List[Run.__response__], resp.json())

    def get(self, project_name: str, run_name: str) -> Run:
        body = GetRunRequest(run_name=run_name)
        json_body = body.json()
        resp = self._request(f"/api/project/{project_name}/runs/get", body=json_body)
        return parse_obj_as(Run.__response__, resp.json())

    def get_plan(self, project_name: str, run_spec: RunSpec) -> RunPlan:
        body = GetRunPlanRequest(run_spec=run_spec)
        resp = self._request(
            f"/api/project/{project_name}/runs/get_plan",
            body=body.json(exclude=_get_run_spec_excludes(run_spec)),
        )
        return parse_obj_as(RunPlan.__response__, resp.json())

    def apply_plan(
        self,
        project_name: str,
        plan: Union[RunPlan, ApplyRunPlanInput],
        force: bool = False,
    ) -> Run:
        plan_input: ApplyRunPlanInput = ApplyRunPlanInput.__response__.parse_obj(plan)
        body = ApplyRunPlanRequest(plan=plan_input, force=force)
        resp = self._request(
            f"/api/project/{project_name}/runs/apply",
            body=body.json(exclude=_get_apply_plan_excludes(plan_input)),
        )
        return parse_obj_as(Run.__response__, resp.json())

    def stop(self, project_name: str, runs_names: List[str], abort: bool):
        body = StopRunsRequest(runs_names=runs_names, abort=abort)
        self._request(f"/api/project/{project_name}/runs/stop", body=body.json())

    def delete(self, project_name: str, runs_names: List[str]):
        body = DeleteRunsRequest(runs_names=runs_names)
        self._request(f"/api/project/{project_name}/runs/delete", body=body.json())


def _get_apply_plan_excludes(plan: ApplyRunPlanInput) -> Optional[Dict]:
    """
    Returns `plan` exclude mapping to exclude certain fields from the request.
    Use this method to exclude new fields when they are not set to keep
    clients backward-compatibility with older servers.
    """
    run_spec_excludes = _get_run_spec_excludes(plan.run_spec)
    if run_spec_excludes is not None:
        return {"plan": run_spec_excludes}
    return None


def _get_run_spec_excludes(run_spec: RunSpec) -> Optional[Dict]:
    """
    Returns `run_spec` exclude mapping to exclude certain fields from the request.
    Use this method to exclude new fields when they are not set to keep
    clients backward-compatibility with older servers.
    """
    spec_excludes: dict[str, Any] = {}
    configuration_excludes: dict[str, Any] = {}
    profile_excludes: set[str] = set()
    # configuration = run_spec.configuration
    # profile = run_spec.profile
    # Fields can be excluded like this:
    # if configuration.availability_zones is None:
    #     configuration_excludes["availability_zones"] = True
    # if profile is not None and profile.availability_zones is None:
    #     profile_excludes.add("availability_zones")
    if configuration_excludes:
        spec_excludes["configuration"] = configuration_excludes
    if profile_excludes:
        spec_excludes["profile"] = profile_excludes
    if spec_excludes:
        return {"run_spec": spec_excludes}
    return None
