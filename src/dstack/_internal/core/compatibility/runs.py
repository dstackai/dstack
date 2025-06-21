from typing import Any, Dict, Optional

from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.runs import ApplyRunPlanInput, JobSubmission, RunSpec
from dstack._internal.server.schemas.runs import GetRunPlanRequest


def get_apply_plan_excludes(plan: ApplyRunPlanInput) -> Optional[Dict]:
    """
    Returns `plan` exclude mapping to exclude certain fields from the request.
    Use this method to exclude new fields when they are not set to keep
    clients backward-compatibility with older servers.
    """
    apply_plan_excludes = {}
    run_spec_excludes = get_run_spec_excludes(plan.run_spec)
    if run_spec_excludes is not None:
        apply_plan_excludes["run_spec"] = run_spec_excludes
    current_resource = plan.current_resource
    if current_resource is not None:
        current_resource_excludes = {}
        current_resource_excludes["status_message"] = True
        if current_resource.deployment_num == 0:
            current_resource_excludes["deployment_num"] = True
        apply_plan_excludes["current_resource"] = current_resource_excludes
        current_resource_excludes["run_spec"] = get_run_spec_excludes(current_resource.run_spec)
        job_submissions_excludes = {}
        current_resource_excludes["jobs"] = {
            "__all__": {"job_submissions": {"__all__": job_submissions_excludes}}
        }
        job_submissions = [js for j in current_resource.jobs for js in j.job_submissions]
        if all(map(_should_exclude_job_submission_jpd_cpu_arch, job_submissions)):
            job_submissions_excludes["job_provisioning_data"] = {
                "instance_type": {"resources": {"cpu_arch"}}
            }
        if all(map(_should_exclude_job_submission_jrd_cpu_arch, job_submissions)):
            job_submissions_excludes["job_runtime_data"] = {
                "offer": {"instance": {"resources": {"cpu_arch"}}}
            }
        if all(js.exit_status is None for js in job_submissions):
            job_submissions_excludes["exit_status"] = True
        if all(js.deployment_num == 0 for js in job_submissions):
            job_submissions_excludes["deployment_num"] = True
        latest_job_submission = current_resource.latest_job_submission
        if latest_job_submission is not None:
            latest_job_submission_excludes = {}
            current_resource_excludes["latest_job_submission"] = latest_job_submission_excludes
            if _should_exclude_job_submission_jpd_cpu_arch(latest_job_submission):
                latest_job_submission_excludes["job_provisioning_data"] = {
                    "instance_type": {"resources": {"cpu_arch"}}
                }
            if _should_exclude_job_submission_jrd_cpu_arch(latest_job_submission):
                latest_job_submission_excludes["job_runtime_data"] = {
                    "offer": {"instance": {"resources": {"cpu_arch"}}}
                }
            if latest_job_submission.exit_status is None:
                latest_job_submission_excludes["exit_status"] = True
            if latest_job_submission.deployment_num == 0:
                latest_job_submission_excludes["deployment_num"] = True
    return {"plan": apply_plan_excludes}


def get_get_plan_excludes(request: GetRunPlanRequest) -> Optional[Dict]:
    """
    Excludes new fields when they are not set to keep
    clients backward-compatibility with older servers.
    """
    get_plan_excludes = {}
    run_spec_excludes = get_run_spec_excludes(request.run_spec)
    if run_spec_excludes is not None:
        get_plan_excludes["run_spec"] = run_spec_excludes
    if request.max_offers is None:
        get_plan_excludes["max_offers"] = True
    return get_plan_excludes


def get_run_spec_excludes(run_spec: RunSpec) -> Optional[Dict]:
    """
    Returns `run_spec` exclude mapping to exclude certain fields from the request.
    Use this method to exclude new fields when they are not set to keep
    clients backward-compatibility with older servers.
    """
    spec_excludes: dict[str, Any] = {}
    configuration_excludes: dict[str, Any] = {}
    profile_excludes: set[str] = set()
    configuration = run_spec.configuration
    profile = run_spec.profile

    if configuration.fleets is None:
        configuration_excludes["fleets"] = True
    if profile is not None and profile.fleets is None:
        profile_excludes.add("fleets")
    if configuration.tags is None:
        configuration_excludes["tags"] = True
    if profile is not None and profile.tags is None:
        profile_excludes.add("tags")
    if isinstance(configuration, ServiceConfiguration) and not configuration.rate_limits:
        configuration_excludes["rate_limits"] = True
    if configuration.shell is None:
        configuration_excludes["shell"] = True
    if configuration.docker is None:
        configuration_excludes["docker"] = True
    if configuration.priority is None:
        configuration_excludes["priority"] = True
    if configuration.startup_order is None:
        configuration_excludes["startup_order"] = True
    if profile is not None and profile.startup_order is None:
        profile_excludes.add("startup_order")
    if configuration.stop_criteria is None:
        configuration_excludes["stop_criteria"] = True
    if profile is not None and profile.stop_criteria is None:
        profile_excludes.add("stop_criteria")

    if configuration_excludes:
        spec_excludes["configuration"] = configuration_excludes
    if profile_excludes:
        spec_excludes["profile"] = profile_excludes
    if spec_excludes:
        return spec_excludes
    return None


def _should_exclude_job_submission_jpd_cpu_arch(job_submission: JobSubmission) -> bool:
    try:
        return job_submission.job_provisioning_data.instance_type.resources.cpu_arch is None
    except AttributeError:
        return True


def _should_exclude_job_submission_jrd_cpu_arch(job_submission: JobSubmission) -> bool:
    try:
        return job_submission.job_runtime_data.offer.instance.resources.cpu_arch is None
    except AttributeError:
        return True
