from typing import Optional

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


def set_gpu_vendor_default(
    resources: ResourcesSpec,
    image: Optional[str],
    docker: Optional[bool],
) -> None:
    """Default GPU vendor to Nvidia when using the default CUDA image,
    since it's only compatible with Nvidia GPUs.
    Mirrors the client-side logic in validate_gpu_vendor_and_image().
    Should only be called for runs (not fleets) since fleets don't have image context."""
    gpu = resources.gpu
    if (
        gpu is not None
        and gpu.vendor is None
        and gpu.name is None
        and gpu.count.max != 0
        and image is None
        and docker is not True
    ):
        gpu.vendor = gpuhunt.AcceleratorVendor.NVIDIA
