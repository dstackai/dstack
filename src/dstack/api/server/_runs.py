from datetime import datetime
from typing import List, Optional, Union
from uuid import UUID

from pydantic import parse_obj_as

from dstack._internal.core.compatibility.runs import (
    get_apply_plan_excludes,
    get_get_plan_excludes,
    get_list_runs_excludes,
)
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
        include_jobs: bool = True,
        job_submissions_limit: Optional[int] = None,
    ) -> List[Run]:
        body = ListRunsRequest(
            project_name=project_name,
            repo_id=repo_id,
            username=username,
            only_active=only_active,
            include_jobs=include_jobs,
            job_submissions_limit=job_submissions_limit,
            prev_submitted_at=prev_submitted_at,
            prev_run_id=prev_run_id,
            limit=limit,
            ascending=ascending,
        )
        resp = self._request(
            "/api/runs/list", body=body.json(exclude=get_list_runs_excludes(body))
        )
        return parse_obj_as(List[Run.__response__], resp.json())

    def get(self, project_name: str, run_name: str) -> Run:
        body = GetRunRequest(run_name=run_name)
        json_body = body.json()
        resp = self._request(f"/api/project/{project_name}/runs/get", body=json_body)
        return parse_obj_as(Run.__response__, resp.json())

    def get_plan(
        self, project_name: str, run_spec: RunSpec, max_offers: Optional[int] = None
    ) -> RunPlan:
        body = GetRunPlanRequest(run_spec=run_spec, max_offers=max_offers)
        resp = self._request(
            f"/api/project/{project_name}/runs/get_plan",
            body=body.json(exclude=get_get_plan_excludes(body)),
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
            body=body.json(exclude=get_apply_plan_excludes(plan_input)),
        )
        return parse_obj_as(Run.__response__, resp.json())

    def stop(self, project_name: str, runs_names: List[str], abort: bool):
        body = StopRunsRequest(runs_names=runs_names, abort=abort)
        self._request(f"/api/project/{project_name}/runs/stop", body=body.json())

    def delete(self, project_name: str, runs_names: List[str]):
        body = DeleteRunsRequest(runs_names=runs_names)
        self._request(f"/api/project/{project_name}/runs/delete", body=body.json())
