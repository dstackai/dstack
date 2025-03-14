from datetime import datetime
from typing import Any, List, Optional, Union
from uuid import UUID

from pydantic import parse_obj_as

from dstack._internal.core.models.common import is_core_model_instance
from dstack._internal.core.models.configurations import (
    STRIP_PREFIX_DEFAULT,
    DevEnvironmentConfiguration,
    ServiceConfiguration,
)
from dstack._internal.core.models.runs import (
    ApplyRunPlanInput,
    Run,
    RunPlan,
    RunSpec,
)
from dstack._internal.core.models.volumes import InstanceMountPoint
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
        # dstack versions prior to 0.18.34 don't support id field, and we don't use it here either
        json_body = body.json(exclude={"id"})
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


def _get_apply_plan_excludes(plan: ApplyRunPlanInput) -> Optional[dict]:
    run_spec_excludes = _get_run_spec_excludes(plan.run_spec)
    if run_spec_excludes is not None:
        return {"plan": run_spec_excludes}
    return None


def _get_run_spec_excludes(run_spec: RunSpec) -> Optional[dict]:
    spec_excludes: dict[str, Any] = {}
    configuration_excludes: dict[str, Any] = {}
    profile_excludes: set[str] = set()
    configuration = run_spec.configuration
    profile = run_spec.profile

    # client >= 0.18.18 / server <= 0.18.17 compatibility tweak
    if not configuration.privileged:
        configuration_excludes["privileged"] = True
    # client >= 0.18.23 / server <= 0.18.22 compatibility tweak
    if configuration.type == "service" and configuration.gateway is None:
        configuration_excludes["gateway"] = True
    # client >= 0.18.30 / server <= 0.18.29 compatibility tweak
    if run_spec.configuration.user is None:
        configuration_excludes["user"] = True
    # client >= 0.18.30 / server <= 0.18.29 compatibility tweak
    if configuration.reservation is None:
        configuration_excludes["reservation"] = True
    if profile is not None and profile.reservation is None:
        profile_excludes.add("reservation")
    if configuration.idle_duration is None:
        configuration_excludes["idle_duration"] = True
    if profile is not None and profile.idle_duration is None:
        profile_excludes.add("idle_duration")
    # client >= 0.18.38 / server <= 0.18.37 compatibility tweak
    if configuration.stop_duration is None:
        configuration_excludes["stop_duration"] = True
    if profile is not None and profile.stop_duration is None:
        profile_excludes.add("stop_duration")
    # client >= 0.18.40 / server <= 0.18.39 compatibility tweak
    if (
        is_core_model_instance(configuration, ServiceConfiguration)
        and configuration.strip_prefix == STRIP_PREFIX_DEFAULT
    ):
        configuration_excludes["strip_prefix"] = True
    if configuration.single_branch is None:
        configuration_excludes["single_branch"] = True
    if all(
        not is_core_model_instance(v, InstanceMountPoint) or not v.optional
        for v in configuration.volumes
    ):
        configuration_excludes["volumes"] = {"__all__": {"optional"}}
    # client >= 0.18.41 / server <= 0.18.40 compatibility tweak
    if configuration.availability_zones is None:
        configuration_excludes["availability_zones"] = True
    if profile is not None and profile.availability_zones is None:
        profile_excludes.add("availability_zones")
    if (
        is_core_model_instance(configuration, DevEnvironmentConfiguration)
        and configuration.inactivity_duration is None
    ):
        configuration_excludes["inactivity_duration"] = True
    if configuration.utilization_policy is None:
        configuration_excludes["utilization_policy"] = True
    if profile is not None and profile.utilization_policy is None:
        profile_excludes.add("utilization_policy")

    if configuration_excludes:
        spec_excludes["configuration"] = configuration_excludes
    if profile_excludes:
        spec_excludes["profile"] = profile_excludes
    if spec_excludes:
        return {"run_spec": spec_excludes}
    return None
