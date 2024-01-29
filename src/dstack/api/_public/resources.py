from typing import List, Optional, Union

from dstack._internal.core.models.resources import (
    DEFAULT_CPU_COUNT,
    DEFAULT_GPU_COUNT,
    DEFAULT_MEMORY_SIZE,
    ComputeCapabilityLike,
    DiskLike,
    DiskSpec,
    DiskSpecSchema,
    GPULike,
    GPUSpec,
    GPUSpecSchema,
    IntRangeLike,
    MemoryLike,
    MemoryRangeLike,
    ResourcesSpec,
    ResourcesSpecSchema,
)


def Resources(
    *,
    cpu: IntRangeLike = DEFAULT_CPU_COUNT,
    memory: MemoryRangeLike = DEFAULT_MEMORY_SIZE,
    gpu: Optional[GPULike] = None,
    shm_size: Optional[MemoryLike] = None,
    disk: Optional[DiskLike] = None,
) -> ResourcesSpec:
    return ResourcesSpec.parse_obj(
        ResourcesSpecSchema(
            cpu=cpu,
            memory=memory,
            gpu=gpu,
            shm_size=shm_size,
            disk=disk,
        )
    )


def GPU(
    *,
    name: Optional[Union[List[str], str]] = None,
    count: IntRangeLike = DEFAULT_GPU_COUNT,
    memory: Optional[MemoryRangeLike] = None,
    total_memory: Optional[MemoryRangeLike] = None,
    compute_capability: Optional[ComputeCapabilityLike] = None,
) -> GPUSpec:
    return GPUSpec.parse_obj(
        GPUSpecSchema(
            name=name,
            count=count,
            memory=memory,
            total_memory=total_memory,
            compute_capability=compute_capability,
        )
    )


def Disk(
    *,
    size: MemoryRangeLike,
) -> DiskSpec:
    return DiskSpec.parse_obj(
        DiskSpecSchema(
            size=size,
        )
    )
