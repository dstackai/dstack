import hashlib
import json
from typing import Any

import gpuhunt

from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.endpoint_presets import (
    EndpointBenchmark,
    EndpointPresetRecipe,
    EndpointPresetValidation,
    EndpointPresetValidationReplica,
)
from dstack._internal.core.models.envs import EnvSentinel
from dstack._internal.core.models.instances import Resources
from dstack._internal.core.models.profiles import ProfileParams
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.utils.common import format_mib_as_gb


def build_endpoint_preset_recipe(
    *,
    service: ServiceConfiguration,
    validation_replicas: list[EndpointPresetValidationReplica],
    base_model: str,
    recipe_model: str,
    context_length: int,
    benchmark: EndpointBenchmark,
) -> EndpointPresetRecipe:
    service = service.copy(deep=True)
    service.name = None
    service.gateway = None
    for field in ProfileParams.__fields__:
        setattr(service, field, None)
    validation = EndpointPresetValidation(
        replicas=validation_replicas,
        benchmark=benchmark,
    )
    set_service_gpu_vendors_from_validations(service, [validation])
    return EndpointPresetRecipe(
        base=base_model,
        id=make_endpoint_preset_recipe_id(service, context_length=context_length),
        model=recipe_model,
        context_length=context_length,
        service=service,
        validations=[validation],
    )


def make_endpoint_preset_recipe_id(
    service: ServiceConfiguration,
    context_length: int,
) -> str:
    payload = json.dumps(
        {
            "service": service_configuration_to_preset_data(service),
            "context_length": context_length,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:8]


def endpoint_preset_recipe_to_data(recipe: EndpointPresetRecipe) -> dict[str, Any]:
    return {
        "base": recipe.base,
        "id": recipe.id,
        "model": recipe.model,
        "context_length": recipe.context_length,
        "service": service_configuration_to_preset_data(recipe.service),
        "validations": [
            json.loads(validation.json(exclude_none=True)) for validation in recipe.validations
        ],
    }


def service_configuration_to_preset_data(
    configuration: ServiceConfiguration,
) -> dict[str, Any]:
    service_data = json.loads(configuration.json(exclude_none=True))
    service_data.pop("type", None)
    service_data.pop("name", None)
    service_data.pop("gateway", None)
    for field in ProfileParams.__fields__:
        service_data.pop(field, None)
    if configuration.env:
        service_data["env"] = [
            _env_item_to_preset_data(key, value)
            for key, value in sorted(configuration.env.items())
        ]
    else:
        service_data.pop("env", None)
    for field, value in list(service_data.items()):
        if value in ({}, []):
            service_data.pop(field)
    return service_data


def resources_spec_from_instance_resources(resources: Resources) -> ResourcesSpec:
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


def set_service_gpu_vendors_from_validations(
    service: ServiceConfiguration,
    validations: list[EndpointPresetValidation],
) -> None:
    for group_num, group in enumerate(service.replica_groups):
        resources = group.resources
        if resources is None or not _requires_gpu(resources):
            continue
        validation_vendor = _get_validation_group_gpu_vendor(validations, group_num)
        if validation_vendor is None or resources.gpu is None:
            continue
        if resources.gpu.vendor is not None and resources.gpu.vendor != validation_vendor:
            raise ValueError("preset service GPU vendor does not match validation")
        group_resources = _get_service_group_resources(service, group_num)
        if group_resources.gpu is not None:
            group_resources.gpu.vendor = validation_vendor


def _env_item_to_preset_data(key: str, value: str | EnvSentinel) -> str:
    if isinstance(value, EnvSentinel):
        return key
    return f"{key}={value}"


def _get_validation_group_gpu_vendor(
    validations: list[EndpointPresetValidation],
    group_num: int,
) -> gpuhunt.AcceleratorVendor | None:
    vendors = {
        vendor
        for validation in validations
        for resources in validation.replicas[group_num].resources
        if (vendor := _get_resources_gpu_vendor(resources)) is not None
    }
    if len(vendors) > 1:
        raise ValueError("preset validations must not mix GPU vendors in a replica group")
    return next(iter(vendors), None)


def _get_resources_gpu_vendor(resources: ResourcesSpec) -> gpuhunt.AcceleratorVendor | None:
    gpu = resources.gpu
    if gpu is None or gpu.count.min == 0:
        return None
    if gpu.vendor is not None:
        return gpu.vendor
    if not gpu.name:
        return None
    vendors = {_get_gpu_name_vendor(name) for name in gpu.name} - {None}
    if len(vendors) > 1:
        raise ValueError("preset validations must not mix GPU vendors in a replica group")
    return next(iter(vendors), None)


def _get_gpu_name_vendor(name: str) -> gpuhunt.AcceleratorVendor | None:
    known = (
        (gpuhunt.KNOWN_NVIDIA_GPUS, gpuhunt.AcceleratorVendor.NVIDIA),
        (gpuhunt.KNOWN_AMD_GPUS, gpuhunt.AcceleratorVendor.AMD),
        (gpuhunt.KNOWN_INTEL_ACCELERATORS, gpuhunt.AcceleratorVendor.INTEL),
        (gpuhunt.KNOWN_TENSTORRENT_ACCELERATORS, gpuhunt.AcceleratorVendor.TENSTORRENT),
    )
    for accelerators, vendor in known:
        if any(accelerator.name.lower() == name.lower() for accelerator in accelerators):
            return vendor
    if name.startswith("tpu-"):
        return gpuhunt.AcceleratorVendor.GOOGLE
    return None


def _get_service_group_resources(
    service: ServiceConfiguration,
    group_num: int,
) -> ResourcesSpec:
    resources = (
        service.replicas[group_num].resources
        if isinstance(service.replicas, list)
        else service.resources
    )
    if resources is None:
        raise ValueError("preset service object must specify resources")
    return resources


def _requires_gpu(resources: ResourcesSpec) -> bool:
    gpu = resources.gpu
    if gpu is None or gpu.count.max == 0:
        return False
    return gpu.count.min != 0 or gpu.count.max is not None
