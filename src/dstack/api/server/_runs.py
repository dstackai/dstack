import copy
from datetime import datetime
from typing import List, Optional, Union
from uuid import UUID

from dstack._internal.core.compatibility.runs import (
    get_apply_plan_excludes,
    get_get_plan_excludes,
    get_list_runs_excludes,
    patch_run_spec,
)
from dstack._internal.core.models.common import validate_extra_ignore
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
            "/api/runs/list", body=body.model_dump_json(exclude=get_list_runs_excludes(body))
        )
        return validate_extra_ignore(List[Run], resp.json())

    def get(
        self, project_name: str, run_name: Optional[str] = None, run_id: Optional[UUID] = None
    ) -> Run:
        if run_name is None and run_id is None:
            raise ValueError("Either run_name or run_id must be provided")
        if run_name is not None and run_id is not None:
            raise ValueError("Cannot specify both run_name and run_id")
        body = GetRunRequest(run_name=run_name, id=run_id)
        json_body = body.model_dump_json()
        resp = self._request(f"/api/project/{project_name}/runs/get", body=json_body)
        return validate_extra_ignore(Run, resp.json())

    def get_plan(
        self,
        project_name: str,
        run_spec: RunSpec,
        max_offers: Optional[int] = None,
        full_offers: bool = False,
        unallocated_resources: bool = False,
        for_offers_only: bool = False,
    ) -> RunPlan:
        body = GetRunPlanRequest(
            run_spec=run_spec,
            max_offers=max_offers,
            full_offers=full_offers,
            unallocated_resources=unallocated_resources,
            for_offers_only=for_offers_only,
        )
        body = copy.deepcopy(body)
        patch_run_spec(body.run_spec)
        resp = self._request(
            f"/api/project/{project_name}/runs/get_plan",
            body=body.model_dump_json(exclude=get_get_plan_excludes(body)),
        )
        return validate_extra_ignore(RunPlan, resp.json())

    def apply_plan(
        self,
        project_name: str,
        plan: Union[RunPlan, ApplyRunPlanInput],
        force: bool = False,
    ) -> Run:
        plan_input = validate_extra_ignore(ApplyRunPlanInput, plan)
        body = ApplyRunPlanRequest(plan=plan_input, force=force)
        body = copy.deepcopy(body)
        patch_run_spec(body.plan.run_spec)
        if body.plan.current_resource is not None:
            patch_run_spec(body.plan.current_resource.run_spec)
        resp = self._request(
            f"/api/project/{project_name}/runs/apply",
            body=body.model_dump_json(exclude=get_apply_plan_excludes(plan_input)),
        )
        return validate_extra_ignore(Run, resp.json())

    def stop(self, project_name: str, runs_names: List[str], abort: bool):
        body = StopRunsRequest(runs_names=runs_names, abort=abort)
        self._request(f"/api/project/{project_name}/runs/stop", body=body.model_dump_json())

    def delete(self, project_name: str, runs_names: List[str]):
        body = DeleteRunsRequest(runs_names=runs_names)
        self._request(f"/api/project/{project_name}/runs/delete", body=body.model_dump_json())
