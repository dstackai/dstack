from typing import Optional

from packaging.version import Version

from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.runs import Run, RunPlan, RunSpec
from dstack._internal.server.compatibility.common import patch_offers_list


def patch_run_plan(run_plan: RunPlan, client_version: Optional[Version]) -> None:
    if client_version is None:
        return
    patch_run_spec(run_plan.run_spec, client_version)
    if run_plan.current_resource is not None:
        patch_run(run_plan.current_resource, client_version)
    for job_plan in run_plan.job_plans:
        patch_offers_list(job_plan.offers, client_version)


def patch_run(run: Run, client_version: Optional[Version]) -> None:
    if client_version is None:
        return
    patch_run_spec(run.run_spec, client_version)


def patch_run_spec(run_spec: RunSpec, client_version: Optional[Version]) -> None:
    if client_version is None:
        return
    # Clients prior to 0.20.8 do not support probes = None
    if client_version < Version("0.20.8") and isinstance(
        run_spec.configuration, ServiceConfiguration
    ):
        if run_spec.configuration.probes is None:
            run_spec.configuration.probes = []
