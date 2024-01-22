from typing import Any, Generic, List, Optional, Tuple, Type, TypeVar, Union

from pydantic import Field, root_validator, validator
from pydantic.generics import GenericModel
from typing_extensions import Annotated

from dstack._internal.core.models.common import ForbidExtra

# TODO(egor-s): add docstrings for API


T = TypeVar("T", bound=Union[int, float])


class Range(GenericModel, Generic[T]):
    min: Optional[Union[T, float, int, str]]
    max: Optional[Union[T, float, int, str]]
    _type: Type[T]

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
            if v == "..":
                raise ValueError("Invalid range: ..")
            min, max = v.split("..")
            return dict(min=min or None, max=max or None)
        if isinstance(v, (str, int, float)):
            return dict(min=v, max=v)
        return v

    @root_validator()
    def _post_validate(cls, values):
        min = values.get("min")
        if min is not None and not isinstance(min, cls._type):
            raise ValueError(f"Invalid min type")

        max = values.get("max")
        if max is not None and not isinstance(max, cls._type):
            raise ValueError(f"Invalid max type")

        if min is None and max is None:
            raise ValueError("Invalid range: ..")
        if min is not None and max is not None and min > max:
            raise ValueError(f"Invalid range order: {min}..{max}")
        return values

    def __str__(self):
        min = repr(self.min) if self.min is not None else ""
        max = repr(self.max) if self.max is not None else ""
        if min == max:
            return min
        return f"{min}..{max}"


class Memory(float):
    """
    Memory size in gigabytes as a float number. Supported units: MB, GB, TB.
    """

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v: Any) -> "Memory":
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


class RangeInt(Range[int]):
    _type = int


class RangeMemory(Range[Memory]):
    _type = Memory


class GPU(ForbidExtra):
    name: Annotated[Optional[List[str]], Field(description="The GPU name or list of names")] = None
    count: Annotated[RangeInt, Field(description="The number of GPUs")] = RangeInt(min=1, max=1)
    memory: Annotated[
        Optional[RangeMemory], Field(description="The VRAM size (e.g., 16GB)")
    ] = None
    total_memory: Annotated[
        Optional[RangeMemory], Field(description="The total VRAM size (e.g., 32GB)")
    ] = None
    compute_capability: Annotated[
        Optional[ComputeCapability],
        Field(description="The minimum compute capability of the GPU (e.g., 7.5)"),
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
        if isinstance(v, str):
            return [v]
        return v


class Disk(ForbidExtra):
    size: Annotated[RangeMemory, Field(description="The disk size (e.g., 100GB)")]

    @classmethod
    def __get_validators__(cls):
        yield cls._parse
        yield cls.validate

    @classmethod
    def _parse(cls, v: Any) -> Any:
        if isinstance(v, (str, int, float)):
            return {"size": v}
        return v


class Resources(ForbidExtra):
    cpu: Annotated[Optional[RangeInt], Field(description="The number of CPU cores")] = RangeInt(
        min=2
    )
    memory: Annotated[
        Optional[RangeMemory], Field(description="The RAM size (e.g., 8GB)")
    ] = RangeMemory(min="8GB")
    shm_size: Annotated[
        Optional[Memory],
        Field(
            description="The size of shared memory (e.g., 8GB). "
            "If you are using parallel communicating processes (e.g., dataloaders in PyTorch), "
            "you may need to configure this."
        ),
    ] = None
    gpu: Annotated[Optional[GPU], Field(description="The GPU resources")] = None
    disk: Annotated[Disk, Field(description="The disk resources")] = None
