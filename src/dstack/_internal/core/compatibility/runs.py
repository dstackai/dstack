from typing import Optional

from dstack._internal.core.compatibility.common import patch_profile_params
from dstack._internal.core.models.common import (
    IncludeExcludeDictType,
    IncludeExcludeSetType,
)
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.routers import SGLangServiceRouterConfig
from dstack._internal.core.models.runs import (
    DEFAULT_PROBE_UNTIL_READY,
    DEFAULT_REPLICA_GROUP_NAME,
    ApplyRunPlanInput,
    JobSpec,
    JobSubmission,
    RunSpec,
)
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
        apply_plan_excludes["current_resource"] = current_resource_excludes
        current_resource_excludes["run_spec"] = get_run_spec_excludes(current_resource.run_spec)
        current_resource_excludes["jobs"] = {
            "__all__": {
                "job_spec": get_job_spec_excludes([job.job_spec for job in current_resource.jobs]),
                "job_submissions": {
                    "__all__": get_job_submission_excludes(
                        [
                            submission
                            for job in current_resource.jobs
                            for submission in job.job_submissions
                        ]
                    ),
                },
                # Contains only informational computed fields, safe to exclude unconditionally
                "job_connection_info": True,
            }
        }
        if current_resource.latest_job_submission is not None:
            current_resource_excludes["latest_job_submission"] = get_job_submission_excludes(
                [current_resource.latest_job_submission]
            )
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

    if isinstance(run_spec.configuration, ServiceConfiguration):
        if run_spec.configuration.probes:
            probe_excludes: IncludeExcludeDictType = {}
            configuration_excludes["probes"] = {"__all__": probe_excludes}
            if all(p.until_ready is None for p in run_spec.configuration.probes):
                probe_excludes["until_ready"] = True
        elif run_spec.configuration.probes is None:
            # Servers prior to 0.20.8 do not support probes=None
            configuration_excludes["probes"] = True

        router = run_spec.configuration.router
        if router is None:
            configuration_excludes["router"] = True
        elif isinstance(router, SGLangServiceRouterConfig) and router.pd_disaggregation is False:
            configuration_excludes["router"] = {"pd_disaggregation": True}
        if run_spec.configuration.https is None:
            configuration_excludes["https"] = True

        replicas = run_spec.configuration.replicas
        if isinstance(replicas, list) and all(g.router is None for g in replicas):
            configuration_excludes["replicas"] = {"__all__": {"router": True}}

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
    if all(s.replica_group == DEFAULT_REPLICA_GROUP_NAME for s in job_specs):
        spec_excludes["replica_group"] = True

    probe_excludes: IncludeExcludeDictType = {}
    spec_excludes["probes"] = {"__all__": probe_excludes}
    if all(all(p.until_ready == DEFAULT_PROBE_UNTIL_READY for p in s.probes) for s in job_specs):
        probe_excludes["until_ready"] = True

    return spec_excludes


def get_job_submission_excludes(job_submissions: list[JobSubmission]) -> IncludeExcludeDictType:
    submission_excludes: IncludeExcludeDictType = {}

    if any(s.job_runtime_data is not None for s in job_submissions):
        jrd_excludes = {}
        if all(
            s.job_runtime_data is None or s.job_runtime_data.username is None
            for s in job_submissions
        ):
            jrd_excludes["username"] = True
        if all(
            s.job_runtime_data is None or s.job_runtime_data.working_dir is None
            for s in job_submissions
        ):
            jrd_excludes["working_dir"] = True
        submission_excludes["job_runtime_data"] = jrd_excludes

    return submission_excludes


def patch_run_spec(run_spec: RunSpec) -> None:
    patch_profile_params(run_spec.configuration)
    if run_spec.profile is not None:
        patch_profile_params(run_spec.profile)
