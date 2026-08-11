from typing import Optional

import gpuhunt

from dstack._internal.core.models.resources import (
    DEFAULT_GPU_SPEC,
    CPUSpec,
    GPUSpec,
    ResourcesSpec,
)
from dstack._internal.utils.gpu import detect_gpu_vendors_by_gpu_name


def set_default_gpu_spec(resources_spec: ResourcesSpec) -> GPUSpec:
    if resources_spec.gpu is None:
        resources_spec.gpu = DEFAULT_GPU_SPEC.model_copy(deep=True)
    return resources_spec.gpu


def set_default_cpu_spec_arch(cpu_spec: CPUSpec, gpu_spec: GPUSpec) -> None:
    if cpu_spec.arch is None:
        if (
            gpu_spec.vendor in [None, gpuhunt.AcceleratorVendor.NVIDIA]
            and gpu_spec.name
            and any(map(gpuhunt.is_nvidia_superchip, gpu_spec.name))
        ):
            cpu_spec.arch = gpuhunt.CPUArchitecture.ARM
        else:
            cpu_spec.arch = gpuhunt.CPUArchitecture.X86


def set_default_gpu_spec_vendor(
    gpu_spec: GPUSpec,
    image: Optional[str],
    docker: Optional[bool],
) -> None:
    """
    Infers and sets the GPU vendor if possible.

    * If the vendor is already set, does nothing.
    * If no GPU requested (max=0), does nothing.
    * If no names are specified (e.g., `gpu: 4`), infers the vendor from the requested image:
        * If the image is not specified and DinD is not requested, that is, the default dstack
        image is used, defaults to NVIDIA, since the image is only compatible with NVIDIA GPUs.
        * Otherwise (the image is set or DinD is requested), does nothing.
    * If names are specified (e.g., `gpu: H100,A100:4`), detects GPU vendors by the names:
        * If all GPU models are known and there is only one vendor, sets that vendor.
        * Otherwise (e.g., `gpu: H100,MI300X` or `gpu: H100,UNKNOWN1000`), does nothing.
    """
    if gpu_spec.vendor is not None:
        return
    if gpu_spec.count.max == 0:
        return
    if not gpu_spec.name:
        if image is None and not docker:
            gpu_spec.vendor = gpuhunt.AcceleratorVendor.NVIDIA
    else:
        # None is a placeholder for an unknown vendor.
        vendors: set[Optional[gpuhunt.AcceleratorVendor]] = set()
        for name in gpu_spec.name:
            _vendors = detect_gpu_vendors_by_gpu_name(name)
            if not _vendors:
                vendors.add(None)
            else:
                vendors.update(_vendors)
        # len(vendors) == 1: Only one vendor or all names are not known (a {None} set).
        # len(vendors) > 1: More than one vendor or some names are not known; in either case, we
        # cannot set the vendor to a specific value, will use only names for matching.
        if len(vendors) == 1:
            gpu_spec.vendor = next(iter(vendors))
