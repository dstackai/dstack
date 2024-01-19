from typing import Any, Generic, List, Optional, Tuple, TypeVar, Union

from pydantic import Field, parse_obj_as, root_validator, validator
from pydantic.generics import GenericModel
from typing_extensions import Annotated

from dstack._internal.core.models.common import ForbidExtra

# TODO(egor-s): add docstrings for API
# TODO(egor-s): polish json schema


T = TypeVar("T")


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
            if v == "..":
                raise ValueError("Invalid range: ..")
            min, max = v.split("..")
            return dict(min=min or None, max=max or None)
        if isinstance(v, (str, int, float)):
            return dict(min=v, max=v)
        return v

    @root_validator()
    def min_ge_max(cls, values):
        min = values.get("min")
        max = values.get("max")
        if min is not None and max is not None and min > max:
            raise ValueError(f"Invalid range order: {min}..{max}")
        return values


class Memory(float):
    """
    Memory size in gigabytes as a float number. Supported units: MB, GB, TB.
    """

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v: Any) -> float:
        if isinstance(v, float):
            return v
        if isinstance(v, int):
            return float(v)
        if isinstance(v, str):
            v = v.replace(" ", "").lower()
            if v.endswith("tb"):
                return cls(v[:-2]) * 1024
            if v.endswith("gb"):
                return cls(v[:-2])
            if v.endswith("mb"):
                return cls(v[:-2]) / 1024
            return cls(v)
        raise ValueError(f"Invalid memory size: {v}")


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


class GPU(ForbidExtra):
    name: Annotated[
        Optional[Union[List[str], str]], Field(description="The GPU name or list of names")
    ] = None
    count: Annotated[Range[int], Field(description="The number of GPUs")] = None
    memory: Annotated[
        Optional[Range[Memory]], Field(description="The VRAM size (e.g., 16GB)")
    ] = None
    total_memory: Annotated[
        Optional[Range[Memory]], Field(description="The total VRAM size (e.g., 32GB)")
    ] = None
    compute_capability: Annotated[
        Optional[ComputeCapability],
        Field(description="The minimum compute capability of the GPU (e.g., 7.5)"),
    ] = None

    @classmethod
    def __get_validators__(cls):
        yield cls._parse
        yield cls.validate

    @classmethod
    def _parse(cls, v: Any) -> Any:
        if isinstance(v, int):
            v = str(v)
        if isinstance(v, str):
            tokens = v.replace(" ", "").split(":")
            spec = {"name": None, "count": None, "memory": None}
            for token in tokens:
                if not token:
                    raise ValueError(f"GPU spec contains empty token: {v}")
                elif token[0].isalpha():  # GPU name is always starts with a letter
                    if spec["name"] is not None:
                        raise ValueError(f"GPU spec name conflict: {v}")
                    spec["name"] = token.split(",")
                    if any(not name for name in spec["name"]):
                        raise ValueError(f"GPU name can not be empty: {v}")
                elif any(c.isalpha() for c in token):  # memory must have a unit
                    if spec["memory"] is not None:
                        raise ValueError(f"GPU spec memory conflict: {v}")
                    spec["memory"] = token
                else:  # count otherwise
                    if spec["count"] is not None:
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
    size: Annotated[Range[Memory], Field(description="The disk size (e.g., 100GB)")]

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
    cpu: Annotated[
        Optional[Range[int]], Field(description="The number of CPU cores")
    ] = parse_obj_as(Range[int], "2..")
    memory: Annotated[
        Optional[Range[Memory]], Field(description="The RAM size (e.g., 8GB)")
    ] = parse_obj_as(Range[Memory], "8GB..")
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
