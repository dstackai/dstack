from typing import Any, Dict, Generic, List, Optional, Tuple, TypeVar, Union

from pydantic import Field, root_validator, validator
from pydantic.generics import GenericModel
from typing_extensions import Annotated

from dstack._internal.core.models.common import ForbidExtra

T = TypeVar("T", bound=Union[int, float])


class Range(GenericModel, Generic[T]):
    min: Optional[T]
    max: Optional[T]

    class Config:
        extra = "forbid"

    @classmethod
    def __get_validators__(cls):
        yield cls._parse
        yield cls.validate

    @classmethod
    def _parse(cls, v: Any) -> Any:
        if isinstance(v, str) and ".." in v:
            v = v.replace(" ", "")
            min, max = v.split("..")
            return dict(min=min or None, max=max or None)
        if isinstance(v, (str, int, float)):
            return dict(min=v, max=v)
        return v

    @root_validator()
    def _post_validate(cls, values):
        min = values.get("min")
        max = values.get("max")

        if min is None and max is None:
            raise ValueError("Invalid empty range: ..")
        if min is not None and max is not None and min > max:
            raise ValueError(f"Invalid range order: {min}..{max}")
        return values

    def __str__(self) -> str:
        min = self.min if self.min is not None else ""
        max = self.max if self.max is not None else ""
        if min == max:
            return str(min)
        return f"{min}..{max}"


class Memory(float):
    """
    Memory size in gigabytes as a float number. Supported units: MB, GB, TB.
    """

    @classmethod
    def __get_validators__(cls):
        yield cls.parse

    @classmethod
    def parse(cls, v: Any) -> "Memory":
        if isinstance(v, (float, int)):
            return cls(v)
        if isinstance(v, str):
            v = v.replace(" ", "").lower()
            if v.endswith("tb"):
                return cls(float(v[:-2]) * 1024)
            if v.endswith("gb"):
                return cls(v[:-2])
            if v.endswith("mb"):
                return cls(float(v[:-2]) / 1024)
            return cls(v)
        raise ValueError(f"Invalid memory size: {v}")

    def __repr__(self):
        return f"{self:g}GB"


class ComputeCapability(Tuple[int, int]):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v: Any) -> Tuple[int, int]:
        if isinstance(v, float):
            v = str(v)
        if isinstance(v, str):
            v = v.strip().split(".")
        if isinstance(v, (tuple, list)):
            if len(v) != 2:
                raise ValueError(f"Invalid compute capability: {v}")
            return int(v[0]), int(v[1])
        raise ValueError(f"Invalid compute capability: {v}")

    def __str__(self):
        return f"{self[0]}.{self[1]}"


DEFAULT_CPU_COUNT = Range[int](min=2)
DEFAULT_MEMORY_SIZE = Range[Memory](min=Memory.parse("8GB"))
DEFAULT_GPU_COUNT = Range[int](min=1, max=1)


class GPUSpec(ForbidExtra):
    """
    The GPU spec

    Attributes:
        name (Optional[List[str]]): The name of the GPU (e.g., `"A100"` or `"H100"`)
        count (Optional[Range[int]]): The number of GPUs
        memory (Optional[Range[Memory]]): The size of a single GPU memory (e.g., `"16GB"`)
        total_memory (Optional[Range[Memory]]): The total size of all GPUs memory (e.g., `"32GB"`)
        compute_capability (Optional[float]): The minimum compute capability of the GPU (e.g., `7.5`)
    """

    name: Optional[List[str]] = None
    count: Range[int] = DEFAULT_GPU_COUNT
    memory: Optional[Range[Memory]] = None
    total_memory: Optional[Range[Memory]] = None
    compute_capability: Optional[ComputeCapability] = None

    @classmethod
    def __get_validators__(cls):
        yield cls.parse
        yield cls.validate

    @classmethod
    def parse(cls, v: Any) -> Any:
        if isinstance(v, int):
            v = str(v)
        if isinstance(v, str):
            tokens = v.replace(" ", "").split(":")
            spec = {}
            for token in tokens:
                if not token:
                    raise ValueError(f"GPU spec contains empty token: {v}")
                elif token[0].isalpha():  # GPU name is always starts with a letter
                    if "name" in spec:
                        raise ValueError(f"GPU spec name conflict: {v}")
                    spec["name"] = token.split(",")
                    if any(not name for name in spec["name"]):
                        raise ValueError(f"GPU name can not be empty: {v}")
                elif any(c.isalpha() for c in token):  # memory must have a unit
                    if "memory" in spec:
                        raise ValueError(f"GPU spec memory conflict: {v}")
                    spec["memory"] = token
                else:  # count otherwise
                    if "count" in spec:
                        raise ValueError(f"GPU spec count conflict: {v}")
                    spec["count"] = token
            return spec
        return v

    @validator("name", pre=True)
    def _validate_name(cls, v: Any) -> Any:
        if v is not None and not isinstance(v, list):
            return [v]
        return v


class DiskSpec(ForbidExtra):
    """
    The disk spec

    Attributes:
        size (Range[Memory]): The size of the disk (e.g., `"100GB"`)
    """

    size: Range[Memory]

    @classmethod
    def __get_validators__(cls):
        yield cls._parse
        yield cls.validate

    @classmethod
    def _parse(cls, v: Any) -> Any:
        if isinstance(v, (str, int, float)):
            return {"size": v}
        return v


class ResourcesSpec(ForbidExtra):
    """
    The minimum resources requirements for the run.

    Attributes:
        cpu (Optional[Range[int]]): The number of CPUs
        memory (Optional[Range[Memory]]): The size of RAM memory (e.g., `"16GB"`)
        gpu (Optional[GPUSpec]): The GPU spec
        shm_size (Optional[Range[Memory]]): The size of shared memory (e.g., `"8GB"`). If you are using parallel communicating processes (e.g., dataloaders in PyTorch), you may need to configure this.
        disk (Optional[DiskSpec]): The disk spec
    """

    class Config:
        @staticmethod
        def schema_extra(schema: Dict[str, Any]):
            schema.clear()
            # replace strict schema with a more permissive one
            ref_template = "#/definitions/ResourcesSpec/definitions/{model}"
            for field, value in ResourcesSpecSchema.schema(ref_template=ref_template).items():
                schema[field] = value

    cpu: Range[int] = DEFAULT_CPU_COUNT
    memory: Range[Memory] = DEFAULT_MEMORY_SIZE
    shm_size: Optional[Memory] = None
    gpu: Optional[GPUSpec] = None
    disk: Optional[DiskSpec] = None


IntRangeLike = Union[Range[Union[int, str]], int, str]
MemoryRangeLike = Union[Range[Union[Memory, float, int, str]], float, int, str]
MemoryLike = Union[Memory, float, int, str]
GPULike = Union[GPUSpec, "GPUSpecSchema", int, str]
DiskLike = Union[DiskSpec, "DiskSpecSchema", float, int, str]
ComputeCapabilityLike = Union[ComputeCapability, float, str]


class GPUSpecSchema(ForbidExtra):
    name: Annotated[
        Optional[Union[List[str], str]], Field(description="The GPU name or list of names")
    ] = None
    count: Annotated[IntRangeLike, Field(description="The number of GPUs")] = DEFAULT_GPU_COUNT
    memory: Annotated[
        Optional[MemoryRangeLike],
        Field(description="The VRAM size (e.g., 16GB)"),
    ] = None
    total_memory: Annotated[
        Optional[MemoryRangeLike],
        Field(description="The total VRAM size (e.g., 32GB)"),
    ] = None
    compute_capability: Annotated[
        Optional[ComputeCapabilityLike],
        Field(description="The minimum compute capability of the GPU (e.g., 7.5)"),
    ] = None


class DiskSpecSchema(ForbidExtra):
    size: Annotated[MemoryRangeLike, Field(description="The disk size (e.g., 100GB)")]


class ResourcesSpecSchema(ForbidExtra):
    cpu: Annotated[
        Optional[IntRangeLike], Field(description="The number of CPU cores")
    ] = DEFAULT_CPU_COUNT
    memory: Annotated[
        Optional[MemoryRangeLike],
        Field(description="The RAM size (e.g., 8GB)"),
    ] = DEFAULT_MEMORY_SIZE
    shm_size: Annotated[
        Optional[MemoryLike],
        Field(
            description="The size of shared memory (e.g., 8GB). "
            "If you are using parallel communicating processes (e.g., dataloaders in PyTorch), "
            "you may need to configure this."
        ),
    ] = None
    gpu: Annotated[Optional[GPULike], Field(description="The GPU resources")] = None
    disk: Annotated[Optional[DiskLike], Field(description="The disk resources")] = None
