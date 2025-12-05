from typing import Optional

from dstack._internal.core.models.common import IncludeExcludeDictType, IncludeExcludeSetType
from dstack._internal.core.models.runs import ApplyRunPlanInput, JobSpec, RunSpec
from dstack._internal.server.schemas.runs import GetRunPlanRequest, ListRunsRequest


def get_list_runs_excludes(list_runs_request: ListRunsRequest) -> IncludeExcludeSetType:
    excludes: IncludeExcludeSetType = set()
    return excludes


def get_apply_plan_excludes(plan: ApplyRunPlanInput) -> Optional[IncludeExcludeDictType]:
    """
    Returns `plan` exclude mapping to exclude certain fields from the request.
    Use this method to exclude new fields when they are not set to keep
    clients backward-compatibility with older servers.
    """
    apply_plan_excludes: IncludeExcludeDictType = {}
    run_spec_excludes = get_run_spec_excludes(plan.run_spec)
    if run_spec_excludes is not None:
        apply_plan_excludes["run_spec"] = run_spec_excludes
    current_resource = plan.current_resource
    if current_resource is not None:
        current_resource_excludes: IncludeExcludeDictType = {}
        current_resource_excludes["run_spec"] = get_run_spec_excludes(current_resource.run_spec)
    return {"plan": apply_plan_excludes}


def get_get_plan_excludes(request: GetRunPlanRequest) -> Optional[IncludeExcludeDictType]:
    """
    Excludes new fields when they are not set to keep
    clients backward-compatibility with older servers.
    """
    get_plan_excludes: IncludeExcludeDictType = {}
    run_spec_excludes = get_run_spec_excludes(request.run_spec)
    if run_spec_excludes is not None:
        get_plan_excludes["run_spec"] = run_spec_excludes
    return get_plan_excludes


def get_run_spec_excludes(run_spec: RunSpec) -> IncludeExcludeDictType:
    """
    Returns `run_spec` exclude mapping to exclude certain fields from the request.
    Use this method to exclude new fields when they are not set to keep
    clients backward-compatibility with older servers.
    """
    spec_excludes: IncludeExcludeDictType = {}
    configuration_excludes: IncludeExcludeDictType = {}
    profile_excludes: IncludeExcludeSetType = set()

    # Add excludes like this:
    #
    # if run_spec.configuration.tags is None:
    #     configuration_excludes["tags"] = True
    # if run_spec.profile is not None and run_spec.profile.tags is None:
    #     profile_excludes.add("tags")

    if configuration_excludes:
        spec_excludes["configuration"] = configuration_excludes
    if profile_excludes:
        spec_excludes["profile"] = profile_excludes
    return spec_excludes


def get_job_spec_excludes(job_specs: list[JobSpec]) -> IncludeExcludeDictType:
    """
    Returns `job_spec` exclude mapping to exclude certain fields from the request.
    Use this method to exclude new fields when they are not set to keep
    clients backward-compatibility with older servers.
    """
    spec_excludes: IncludeExcludeDictType = {}
    return spec_excludes
