import gpuhunt
from pydantic import parse_obj_as

from dstack._internal.core.models.resources import CPUSpec, ResourcesSpec


def set_resources_defaults(resources: ResourcesSpec) -> None:
    # TODO: Remove in 0.20. Use resources.cpu directly
    cpu = parse_obj_as(CPUSpec, resources.cpu)
    if cpu.arch is None:
        gpu = resources.gpu
        if (
            gpu is not None
            and gpu.vendor in [None, gpuhunt.AcceleratorVendor.NVIDIA]
            and gpu.name
            and any(map(gpuhunt.is_nvidia_superchip, gpu.name))
        ):
            cpu.arch = gpuhunt.CPUArchitecture.ARM
        else:
            cpu.arch = gpuhunt.CPUArchitecture.X86
        resources.cpu = cpu
