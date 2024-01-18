from typing import Any, Generic, List, Optional, Tuple, TypeVar, Union

from pydantic import BaseModel, Field, parse_obj_as
from pydantic.generics import GenericModel
from typing_extensions import Annotated

# TODO(egor-s): implement ForbidExtra recursive validator


T = TypeVar("T")


class Range(GenericModel, Generic[T]):
    min: Optional[T]
    max: Optional[T]

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
                return Memory(v[:-2]) * 1024
            if v.endswith("gb"):
                return Memory(v[:-2])
            if v.endswith("mb"):
                return Memory(v[:-2]) / 1024
            return Memory(v)
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


class Gpu(BaseModel):
    name: Annotated[
        Optional[Union[str, List[str]]], Field(description="The GPU name or list of names")
    ] = None
    count: Annotated[Range[int], Field(description="The number of GPUs")] = Range[int](
        min=1, max=1
    )
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
            pass  # TODO(egor-s)
        return v


class Resources(BaseModel):
    cpu: Annotated[
        Optional[Range[int]], Field(description="The number of CPU cores")
    ] = parse_obj_as(Range[int], "2..")
    memory: Annotated[
        Optional[Range[Memory]], Field(description="The RAM size (e.g., 8GB)")
    ] = parse_obj_as(Range[Memory], "8GB..")
    gpu: Annotated[Optional[Gpu], Field(description="The GPU resources")] = None
    disk: Annotated[
        Optional[Range[Memory]], Field(description="The disk size (e.g., 100GB)")
    ] = parse_obj_as(Range[Memory], "100GB..")
