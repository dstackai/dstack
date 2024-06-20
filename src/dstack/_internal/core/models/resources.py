from typing import Any, Dict, Generic, List, Optional, Tuple, TypeVar, Union

from pydantic import Field, root_validator, validator
from pydantic.generics import GenericModel
from typing_extensions import Annotated

from dstack._internal.core.models.common import CoreModel

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


class GPUSpec(CoreModel):
    name: Annotated[
        Optional[List[str]], Field(description="The name of the GPU (e.g., `A100` or `H100`)")
    ] = None
    count: Annotated[Range[int], Field(description="The number of GPUs")] = DEFAULT_GPU_COUNT
    memory: Annotated[
        Optional[Range[Memory]],
        Field(
            description="The RAM size (e.g., `16GB`). Can be set to a range (e.g. `16GB..`, or `16GB..80GB`)"
        ),
    ] = None
    total_memory: Annotated[
        Optional[Range[Memory]],
        Field(
            description="The total RAM size (e.g., `32GB`). Can be set to a range (e.g. `16GB..`, or `16GB..80GB`)"
        ),
    ] = None
    compute_capability: Annotated[
        Optional[ComputeCapability],
        Field(description="The minimum compute capability of the GPU (e.g., `7.5`)"),
    ] = None

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


MIN_DISK_SIZE = 50


class DiskSpec(CoreModel):
    size: Annotated[Range[Memory], Field(description="Disk size")]

    @classmethod
    def __get_validators__(cls):
        yield cls._parse
        yield cls.validate

    @classmethod
    def _parse(cls, v: Any) -> Any:
        if isinstance(v, (str, int, float)):
            return {"size": v}
        return v

    @validator("size")
    def validate_size(cls, size):
        if size.min is not None and size.min < MIN_DISK_SIZE:
            raise ValueError(f"Min disk size should be >= {MIN_DISK_SIZE}GB")
        if size.max is not None and size.max < MIN_DISK_SIZE:
            raise ValueError(f"Max disk size should be >= {MIN_DISK_SIZE}GB")
        return size


DEFAULT_DISK = DiskSpec(size=Range[Memory](min=Memory.parse("100GB"), max=None))


class ResourcesSpec(CoreModel):
    class Config:
        @staticmethod
        def schema_extra(schema: Dict[str, Any]):
            schema.clear()
            # replace strict schema with a more permissive one
            ref_template = "#/definitions/ResourcesSpecRequest/definitions/{model}"
            for field, value in ResourcesSpecSchema.schema(ref_template=ref_template).items():
                schema[field] = value

    cpu: Annotated[Range[int], Field(description="The number of CPU cores")] = DEFAULT_CPU_COUNT
    memory: Annotated[Range[Memory], Field(description="The RAM size (e.g., `8GB`)")] = (
        DEFAULT_MEMORY_SIZE
    )
    shm_size: Annotated[
        Optional[Memory],
        Field(
            description="The size of shared memory (e.g., `8GB`). "
            "If you are using parallel communicating processes (e.g., dataloaders in PyTorch), "
            "you may need to configure this"
        ),
    ] = None
    gpu: Annotated[Optional[GPUSpec], Field(description="The GPU requirements")] = None
    disk: Annotated[Optional[DiskSpec], Field(description="The disk resources")] = DEFAULT_DISK


IntRangeLike = Union[Range[Union[int, str]], int, str]
MemoryRangeLike = Union[Range[Union[Memory, float, int, str]], float, int, str]
MemoryLike = Union[Memory, float, int, str]
GPULike = Union[GPUSpec, "GPUSpecSchema", int, str]
DiskLike = Union[DiskSpec, "DiskSpecSchema", float, int, str]
ComputeCapabilityLike = Union[ComputeCapability, float, str]


class GPUSpecSchema(CoreModel):
    name: Annotated[
        Optional[Union[List[str], str]], Field(description="The GPU name or list of names")
    ] = None
    count: Annotated[IntRangeLike, Field(description="The number of GPUs")] = DEFAULT_GPU_COUNT
    memory: Annotated[
        Optional[MemoryRangeLike],
        Field(
            description="The RAM size (e.g., `16GB`). Can be set to a range (e.g. `16GB..`, or `16GB..80GB`)"
        ),
    ] = None
    total_memory: Annotated[
        Optional[MemoryRangeLike],
        Field(
            description="The total RAM size (e.g., `32GB`). Can be set to a range (e.g. `16GB..`, or `16GB..80GB`)"
        ),
    ] = None
    compute_capability: Annotated[
        Optional[ComputeCapabilityLike],
        Field(description="The minimum compute capability of the GPU (e.g., `7.5`)"),
    ] = None


class DiskSpecSchema(CoreModel):
    size: Annotated[
        MemoryRangeLike,
        Field(
            description="The disk size. Can be a string (e.g., `100GB` or `100GB..`) or an object"
            "; see [examples](#examples)"
        ),
    ]


class ResourcesSpecSchema(CoreModel):
    cpu: Annotated[Optional[IntRangeLike], Field(description="The number of CPU cores")] = (
        DEFAULT_CPU_COUNT
    )
    memory: Annotated[
        Optional[MemoryRangeLike],
        Field(description="The RAM size (e.g., `8GB`)"),
    ] = DEFAULT_MEMORY_SIZE
    shm_size: Annotated[
        Optional[MemoryLike],
        Field(
            description="The size of shared memory (e.g., `8GB`). "
            "If you are using parallel communicating processes (e.g., dataloaders in PyTorch), "
            "you may need to configure this"
        ),
    ] = None
    gpu: Annotated[
        Optional[GPULike],
        Field(
            description="The GPU requirements. Can be set to a number, a string (e.g. `A100`, `80GB:2`, etc.), or an object; see [examples](#examples)"
        ),
    ] = None
    disk: Annotated[Optional[DiskLike], Field(description="The disk resources")] = DEFAULT_DISK
