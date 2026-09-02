from typing import Optional

from packaging.version import Version

from dstack._internal.core.models.common import EntityReference
from dstack._internal.core.models.configurations import (
    SERVICE_HTTPS_DEFAULT,
    ServiceConfiguration,
    TaskConfiguration,
)
from dstack._internal.core.models.runs import Run, RunPlan, RunSpec
from dstack._internal.server.compatibility.common import patch_profile_params


def patch_run_plan(run_plan: RunPlan, client_version: Optional[Version]) -> None:
    if client_version is None:
        return
    patch_run_spec(run_plan.run_spec, client_version)
    if run_plan.effective_run_spec is not None:
        patch_run_spec(run_plan.effective_run_spec, client_version)
    if run_plan.current_resource is not None:
        patch_run(run_plan.current_resource, client_version)


def patch_run(run: Run, client_version: Optional[Version]) -> None:
    if client_version is None:
        return
    patch_run_spec(run.run_spec, client_version)


def patch_run_spec(run_spec: RunSpec, client_version: Optional[Version]) -> None:
    if client_version is None:
        return
    # Clients prior to 0.21.3 do not support `groups` on services
    if (
        client_version < Version("0.21.3")
        and isinstance(run_spec.configuration, ServiceConfiguration)
        and run_spec.configuration.groups is not None
    ):
        groups = [group.model_dump(mode="json") for group in run_spec.configuration.groups]
        for group in groups:
            group["count"] = group.pop("replicas")
        # `replicas` was a list of replica groups in old clients but is now typed
        # `Optional[Range[int]]`. Safe to ignore: pydantic validates on parse, not
        # on assignment, and serializes the value as set.
        run_spec.configuration.replicas = groups  # type: ignore[assignment]
        run_spec.configuration.groups = None
    # Clients that type nodes as int reject null. Homogeneous default is 1.
    if (
        isinstance(run_spec.configuration, TaskConfiguration)
        and run_spec.configuration.groups is None
        and run_spec.configuration.nodes is None
    ):
        run_spec.configuration.nodes = 1
    # Clients prior to 0.20.8 do not support probes = None
    if client_version < Version("0.20.8") and isinstance(
        run_spec.configuration, ServiceConfiguration
    ):
        if run_spec.configuration.probes is None:
            run_spec.configuration.probes = []
    # Clients prior to 0.20.12 do not support https = None
    if (
        client_version < Version("0.20.12")
        and isinstance(run_spec.configuration, ServiceConfiguration)
        and run_spec.configuration.https is None
    ):
        run_spec.configuration.https = SERVICE_HTTPS_DEFAULT
    patch_profile_params(run_spec.configuration, client_version)
    if run_spec.profile is not None:
        patch_profile_params(run_spec.profile, client_version)
    # Clients prior to 0.20.20 do not support `EntityReference` in `gateway`
    if (
        client_version < Version("0.20.20")
        and isinstance(run_spec.configuration, ServiceConfiguration)
        and isinstance(run_spec.configuration.gateway, EntityReference)
    ):
        run_spec.configuration.gateway = run_spec.configuration.gateway.format()


def is_run_plan_for_offers_only(
    run_spec: RunSpec, for_offers_only: bool, client_version: Optional[Version]
) -> bool:
    """
    Clients < 0.21.0 don't support `for_offers_only` argument and rely on a magic configuration
    that triggers "offer collection only" path.

    TODO: Drop once clients < 0.21.0 are no longer supported.

    NOTE: A real task with `commands == [":"]` would also match this special `dstack offer` path.
    """
    if for_offers_only:
        return True
    if client_version is not None and client_version < Version("0.21.0"):
        return run_spec.configuration.type == "task" and run_spec.configuration.commands == [":"]
    return False
