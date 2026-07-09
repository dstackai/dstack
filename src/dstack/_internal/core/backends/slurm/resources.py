import dataclasses
from typing import Optional

import gpuhunt
from typing_extensions import Self

from dstack._internal.core.models.instances import Gpu
from dstack._internal.core.models.resources import (
    DEFAULT_MEMORY_SIZE,
    CPUSpec,
    Memory,
    ResourcesSpec,
)


@dataclasses.dataclass
class Node:
    name: str
    arch: Optional[str]
    cpus: int
    memory_mib: int
    gres: list[str]
    partitions: list[str]


@dataclasses.dataclass
class ResolvedNode(Node):
    hostname: str
    ip: str


def parse_gres_gpu_count(gres: str) -> int:
    """
    Parse the number of GPUs from a single GRES entry, e.g. `gpu:8`, `gpu:tesla:2`,
    `gpu:tesla:4(S:0-1)` (the `gpu[:type]:count[(S:sockets)]` format).

    Returns 0 for non-`gpu` GRES entries. Raises `ValueError` if it is a `gpu` entry
    but the count cannot be parsed.
    """
    if not gres.startswith("gpu:"):
        return 0
    # Strip the optional socket affinity suffix, e.g. gpu:tesla:4(S:0-1) -> gpu:tesla:4
    spec = gres.split("(", maxsplit=1)[0]
    return int(spec.rsplit(":", maxsplit=1)[-1])


@dataclasses.dataclass(frozen=True)
class GPUModel:
    vendor: gpuhunt.AcceleratorVendor
    name: str
    memory_mib: int

    def __str__(self) -> str:
        return f"{self.vendor.value}:{self.name}:{round(self.memory_mib / 1024)}GB"

    @classmethod
    def from_string(cls, s: str) -> Self:
        fields = [f for _f in s.split(":") if (f := _f.strip())]
        if not fields or len(fields) > 3:
            raise ValueError("Invalid format")

        vendor_raw: Optional[str] = None
        name_raw: Optional[str] = None
        memory_raw: Optional[str] = None

        if len(fields) == 3:
            [vendor_raw, name_raw, memory_raw] = fields
        elif len(fields) == 1:
            [name_raw] = fields
        else:
            try:
                gpuhunt.AcceleratorVendor.cast(fields[0])
            except ValueError:
                [name_raw, memory_raw] = fields
            else:
                [vendor_raw, name_raw] = fields

        vendor: Optional[gpuhunt.AcceleratorVendor] = None
        if vendor_raw is not None:
            vendor = gpuhunt.AcceleratorVendor(vendor_raw)
        memory: Optional[Memory] = None
        if memory_raw is not None:
            memory = Memory.parse(memory_raw)

        if vendor is not None and memory is not None:
            return cls(
                vendor=vendor,
                name=name_raw,
                memory_mib=round(memory * 1024),
            )
        accelerators = gpuhunt.find_accelerators(
            names=[name_raw.replace(" ", "")],
            vendors=[vendor] if vendor is not None else None,
        )
        if memory is not None:
            memory_gib = round(memory)
            accelerators = [a for a in accelerators if a.memory == memory_gib]
        if not accelerators:
            raise ValueError(f"No matching GPU model found: {s}")
        if len(accelerators) > 1:
            raise ValueError(f"Multiple matching GPU models found: {s}: {accelerators}")
        accelerator = accelerators[0]
        return cls(
            vendor=accelerator.vendor,
            name=accelerator.name,
            memory_mib=accelerator.memory * 1024,
        )

    def to_gpu(self) -> Gpu:
        return Gpu(vendor=self.vendor, name=self.name, memory_mib=self.memory_mib)


@dataclasses.dataclass
class RequestedResources:
    cpu_count: int
    memory_mib: int
    gpu_count: int
    disk_mib: int


def get_requested_resources_from_resources_spec(spec: ResourcesSpec) -> RequestedResources:
    assert isinstance(spec.cpu, CPUSpec)
    # 1 is the default value of --cpus-per-task
    cpu_count = spec.cpu.count.min or 1

    # We cannot use 0 as a fallback since --mem=0 is a special case
    # We cannot infer the default value which Slurm will use since it's partition-specific
    # The easiest/safest option is to use some sane default
    memory = spec.memory.min or DEFAULT_MEMORY_SIZE.min
    assert memory
    if spec.memory.max:
        memory = min(memory, spec.memory.max)
    memory_mib = round(memory * 1024)

    gpu_count: int = 0
    if spec.gpu is not None:
        gpu_count = spec.gpu.count.min or 0

    disk_mib: int = 0
    if spec.disk is not None:
        disk_mib = round((spec.disk.size.min or 0) * 1024)

    return RequestedResources(
        cpu_count=cpu_count,
        memory_mib=memory_mib,
        gpu_count=gpu_count,
        disk_mib=disk_mib,
    )
