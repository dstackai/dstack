from datetime import datetime
from typing import Any, Optional, TypeVar

import gpuhunt

from dstack._internal.cli.models.presets import (
    PRESET_EXCLUDED_FIELDS,
    PresetBenchmark,
    PresetVerificationReplicaGroup,
    VerifiedPreset,
)
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.envs import Env, EnvSentinel
from dstack._internal.core.models.instances import Resources
from dstack._internal.core.models.presets import PresetConfiguration
from dstack._internal.core.models.resources import (
    CPUSpec,
    DiskSpec,
    GPUSpec,
    Memory,
    Range,
    ResourcesSpec,
)
from dstack._internal.utils.gpu import detect_gpu_vendors_by_gpu_name

ConfigurationT = TypeVar("ConfigurationT", ServiceConfiguration, PresetConfiguration)


def build_preset(
    *,
    service: ServiceConfiguration,
    verification_replica_groups: list[PresetVerificationReplicaGroup],
    base_model: str,
    model: str,
    context_length: int,
    benchmark: PresetBenchmark,
    configuration: PresetConfiguration,
    best_trial: int,
    preset_id: str,
    name: Optional[str],
    submitted_at: datetime,
) -> VerifiedPreset:
    service = _without_excluded_fields(service)
    configuration = _without_excluded_fields(configuration)
    configuration.env = Env()
    set_service_gpu_vendor_from_verification(service, verification_replica_groups)
    return VerifiedPreset(
        name=name,
        base=base_model,
        id=preset_id,
        model=model,
        context_length=context_length,
        best_trial=best_trial,
        configuration=configuration,
        submitted_at=submitted_at,
        service=service,
        benchmark=benchmark,
        verified_on=verification_replica_groups,
    )


def preset_to_yaml_dict(preset: VerifiedPreset) -> dict[str, Any]:
    """`VerifiedPreset` in the plain types `yaml.safe_dump` accepts."""
    return {
        # A saved preset is verified by definition; `status` is wire-only.
        **preset.model_dump(mode="json", exclude_none=True, exclude={"status"}),
        "service": service_configuration_to_yaml_dict(preset.service),
    }


def service_configuration_to_yaml_dict(
    configuration: ServiceConfiguration,
) -> dict[str, Any]:
    """The service as a preset stores it.

    Env is rewritten as `key=value` because dumping it writes a passthrough
    variable as `HF_TOKEN: {key: HF_TOKEN}`, and this file is meant to be read."""
    service = configuration.model_dump(
        mode="json",
        exclude={"type", *PRESET_EXCLUDED_FIELDS},
        exclude_none=True,
    )
    if configuration.env:
        service["env"] = [
            _env_item_to_yaml(key, value) for key, value in sorted(configuration.env.items())
        ]
    return {field: value for field, value in service.items() if value not in ({}, [])}


def resources_spec_from_instance_resources(resources: Resources) -> ResourcesSpec:
    gpu = GPUSpec(count=Range[int](min=0, max=0))
    if resources.gpus:
        first = resources.gpus[0]
        if any(
            (g.name, g.memory_mib, g.vendor) != (first.name, first.memory_mib, first.vendor)
            for g in resources.gpus
        ):
            raise ValueError("preset cannot be built from mixed-GPU instances")
        gpu = GPUSpec(
            vendor=first.vendor,
            name=[first.name],
            count=_exact(len(resources.gpus)),
            memory=_exact_memory(first.memory_mib),
        )
    return ResourcesSpec(
        cpu=CPUSpec(arch=resources.cpu_arch, count=_exact(resources.cpus)),
        memory=_exact_memory(resources.memory_mib),
        disk=DiskSpec(size=_exact_memory(resources.disk.size_mib)),
        gpu=gpu,
    )


def _exact(value: int) -> Range[int]:
    return Range[int](min=value, max=value)


def _exact_memory(mib: int) -> Range[Memory]:
    # Rounded to what a user would write in `resources`: 128887MiB is 125.9GB.
    size = Memory(round(mib / 1024, 1))
    return Range[Memory](min=size, max=size)


def set_service_gpu_vendor_from_verification(
    service: ServiceConfiguration,
    verified_on: list[PresetVerificationReplicaGroup],
) -> None:
    for group_num, group in enumerate(service.replica_groups):
        resources = group.resources
        if resources is None or not _requires_gpu(resources):
            continue
        verification_vendor = _get_verification_group_gpu_vendor(verified_on, group.name)
        if verification_vendor is None or resources.gpu is None:
            continue
        if resources.gpu.vendor is not None and resources.gpu.vendor != verification_vendor:
            raise ValueError("preset service GPU vendor does not match verification")
        group_resources = _get_service_group_resources(service, group_num)
        if group_resources.gpu is not None:
            group_resources.gpu.vendor = verification_vendor


def _without_excluded_fields(configuration: ConfigurationT) -> ConfigurationT:
    return configuration.model_copy(deep=True, update=dict.fromkeys(PRESET_EXCLUDED_FIELDS))


def _env_item_to_yaml(key: str, value: str | EnvSentinel) -> str:
    if isinstance(value, EnvSentinel):
        return key
    return f"{key}={value}"


def _get_verification_group_gpu_vendor(
    verified_on: list[PresetVerificationReplicaGroup],
    group_name: str,
) -> gpuhunt.AcceleratorVendor | None:
    vendors = {
        vendor
        for group in verified_on
        if group.name == group_name
        for resources in group.replicas
        if (vendor := _get_resources_gpu_vendor(resources)) is not None
    }
    if len(vendors) > 1:
        raise ValueError("preset verification must not mix GPU vendors in a replica group")
    return next(iter(vendors), None)


def _get_resources_gpu_vendor(resources: ResourcesSpec) -> gpuhunt.AcceleratorVendor | None:
    gpu = resources.gpu
    if gpu is None or gpu.count.min == 0:
        return None
    if gpu.vendor is not None:
        return gpu.vendor
    if not gpu.name:
        return None
    vendors: set[gpuhunt.AcceleratorVendor] = set()
    for name in gpu.name:
        vendors.update(detect_gpu_vendors_by_gpu_name(name))
    if len(vendors) > 1:
        raise ValueError("preset verification must not mix GPU vendors in a replica group")
    return next(iter(vendors), None)


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
