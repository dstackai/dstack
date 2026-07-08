from collections import defaultdict
from typing import Any

from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.instances import InstanceOfferWithAvailability, Resources
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server.models import JobModel, RunModel
from dstack._internal.server.services import jobs as jobs_services
from dstack._internal.server.services import runs as runs_services
from dstack._internal.server.services.endpoints.presets import (
    EndpointPreset,
    EndpointPresetRecipe,
    EndpointPresetValidation,
    EndpointPresetValidationReplica,
    make_endpoint_preset_recipe_id,
    set_service_gpu_vendors_from_validations,
)
from dstack._internal.utils.common import format_mib_as_gb


def build_endpoint_preset_from_run(run_model: RunModel) -> EndpointPreset:
    run_spec = runs_services.get_run_spec(run_model)
    configuration = run_spec.configuration
    if not isinstance(configuration, ServiceConfiguration):
        raise ValueError("endpoint preset can only be built from a service run")
    if configuration.model is None:
        raise ValueError("endpoint preset service must specify model")

    jobs_by_group = _get_current_registered_replica_jobs_by_group(run_model)
    validation_replicas = []
    for replica_group in configuration.replica_groups:
        group_name = replica_group.name
        if group_name is None:
            raise ValueError("endpoint preset cannot be built from unnamed service replicas")
        group_jobs = jobs_by_group.get(group_name, [])
        if not group_jobs:
            raise ValueError(
                f"endpoint preset cannot be built: replica group {group_name!r} "
                "has no registered running replicas"
            )
        validation_replicas.append(
            EndpointPresetValidationReplica(
                resources=[_get_job_resources_spec(job) for job in group_jobs],
            )
        )

    service = configuration.copy(deep=True)
    service.name = None
    validation = EndpointPresetValidation(replicas=validation_replicas)
    set_service_gpu_vendors_from_validations(
        service=service,
        validations=[validation],
    )
    return EndpointPreset(
        model=configuration.model.name,
        recipes=[
            EndpointPresetRecipe(
                id=make_endpoint_preset_recipe_id(service),
                service=service,
                validations=[validation],
            )
        ],
    )


def _get_current_registered_replica_jobs_by_group(
    run_model: RunModel,
) -> dict[str, list[JobModel]]:
    jobs_by_group = defaultdict(list)
    for job in sorted(run_model.jobs, key=lambda j: (j.replica_num, j.job_num)):
        if job.deployment_num != run_model.deployment_num:
            continue
        if job.job_num != 0:
            continue
        if job.status != JobStatus.RUNNING or not job.registered:
            continue
        job_spec = jobs_services.get_job_spec(job)
        jobs_by_group[job_spec.replica_group].append(job)
    return jobs_by_group


def _get_job_resources_spec(job_model: JobModel) -> ResourcesSpec:
    offer = _get_job_offer(job_model)
    if offer is None:
        raise ValueError("endpoint preset cannot be built without actual instance resources")
    return _resources_spec_from_instance_resources(offer.instance.resources)


def _get_job_offer(job_model: JobModel) -> InstanceOfferWithAvailability | None:
    job_runtime_data = jobs_services.get_job_runtime_data(job_model)
    if job_runtime_data is not None and job_runtime_data.offer is not None:
        return job_runtime_data.offer
    instance = job_model.__dict__.get("instance")
    if instance is not None and instance.offer is not None:
        return InstanceOfferWithAvailability.__response__.parse_raw(instance.offer)
    return None


def _resources_spec_from_instance_resources(resources: Resources) -> ResourcesSpec:
    data: dict[str, Any] = {
        "cpu": str(resources.cpus),
        "memory": format_mib_as_gb(resources.memory_mib),
        "disk": format_mib_as_gb(resources.disk.size_mib),
    }
    if resources.cpu_arch is not None:
        data["cpu"] = f"{resources.cpu_arch.value}:{resources.cpus}"
    if resources.gpus:
        first_gpu = resources.gpus[0]
        if any(
            gpu.name != first_gpu.name
            or gpu.memory_mib != first_gpu.memory_mib
            or gpu.vendor != first_gpu.vendor
            for gpu in resources.gpus
        ):
            raise ValueError("endpoint preset cannot be built from mixed-GPU instances")
        data["gpu"] = {
            "name": first_gpu.name,
            "memory": format_mib_as_gb(first_gpu.memory_mib),
            "count": len(resources.gpus),
        }
        if first_gpu.vendor is not None:
            data["gpu"]["vendor"] = first_gpu.vendor.value
    else:
        data["gpu"] = 0
    return ResourcesSpec.parse_obj(data)
