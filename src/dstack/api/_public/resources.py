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


# TODO(andrey): This method looks like a workaround and possibly must be reworked (replaced with something else).
#   Currently it's only used by the `dstack pool add` command.
def Resources(
    *,
    cpu: IntRangeLike = DEFAULT_CPU_COUNT,
    memory: MemoryRangeLike = DEFAULT_MEMORY_SIZE,
    gpu: Optional[GPULike] = None,
    shm_size: Optional[MemoryLike] = None,
    disk: Optional[DiskLike] = None,
) -> ResourcesSpec:
    """
    Creates required resources specification.

    Args:
        cpu (Optional[Range[int]]): The number of CPUs
        memory (Optional[Range[Memory]]): The size of RAM memory (e.g., `"16GB"`)
        gpu (Optional[GPUSpec]): The GPU spec
        shm_size (Optional[Range[Memory]]): The of shared memory (e.g., `"8GB"`). If you are using parallel communicating processes (e.g., dataloaders in PyTorch), you may need to configure this.
        disk (Optional[DiskSpec]): The disk spec

    Returns:
        resources specification
    """
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
    """
    Creates GPU specification.

    Args:
        name (Optional[List[str]]): The name of the GPU (e.g., `"A100"` or `"H100"`)
        count (Optional[Range[int]]): The number of GPUs
        memory (Optional[Range[Memory]]): The size of a single GPU memory (e.g., `"16GB"`)
        total_memory (Optional[Range[Memory]]): The total size of all GPUs memory (e.g., `"32GB"`)
        compute_capability (Optional[float]): The minimum compute capability of the GPU (e.g., `7.5`)

    Returns:
        GPU specification
    """
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
    """
    Creates disk specification.

    Args:
        size (Range[Memory]): The size of the disk (e.g., `"100GB"`)

    Returns:
        disk specification
    """
    return DiskSpec.parse_obj(
        DiskSpecSchema(
            size=size,
        )
    )
