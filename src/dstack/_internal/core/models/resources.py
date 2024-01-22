from typing import Any, Generic, List, Optional, Tuple, TypeVar, Union

from pydantic import Field, root_validator, validator
from pydantic.fields import ModelField
from pydantic.generics import GenericModel
from typing_extensions import Annotated, get_args, get_origin

from dstack._internal.core.models.common import ForbidExtra

# TODO(egor-s): add docstrings for API


def force_type(v: Any, field: ModelField) -> Any:
    """
    Force the first argument of the Union.
    The rest of the options are presented for flexible typing only.
    """
    origin, args = get_origin(field.type_), get_args(field.type_)
    if origin is Union:
        # this check is safe for required fields too
        if not isinstance(v, (args[0], type(None))):
            raise ValueError("Invalid type")
    return v


T = TypeVar("T", bound=Union[int, float])


class Range(GenericModel, Generic[T]):
    min: Optional[Union[T, float, int, str]]
    max: Optional[Union[T, float, int, str]]

    _force_type = validator("*", allow_reuse=True)(force_type)

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

    def __str__(self):
        min = self.min if self.min is not None else ""
        max = self.max if self.max is not None else ""
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


class GPU(ForbidExtra):
    name: Annotated[
        Optional[Union[List[str], str]], Field(description="The GPU name or list of names")
    ] = None
    count: Annotated[Union[Range[int], int, str], Field(description="The number of GPUs")] = Range[
        int
    ](min=1, max=1)
    memory: Annotated[
        Optional[Union[Range[Memory], float, int, str]],
        Field(description="The VRAM size (e.g., 16GB)"),
    ] = None
    total_memory: Annotated[
        Optional[Union[Range[Memory], float, int, str]],
        Field(description="The total VRAM size (e.g., 32GB)"),
    ] = None
    compute_capability: Annotated[
        Optional[Union[ComputeCapability, float, str]],
        Field(description="The minimum compute capability of the GPU (e.g., 7.5)"),
    ] = None

    _force_type = validator(
        "count", "memory", "total_memory", "compute_capability", allow_reuse=True
    )(force_type)

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
        if not isinstance(v, list):
            return [v]
        return v


class Disk(ForbidExtra):
    size: Annotated[
        Union[Range[Memory], float, int, str], Field(description="The disk size (e.g., 100GB)")
    ]

    _force_type = validator("size", allow_reuse=True)(force_type)

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
        Optional[Union[Range[int], int, str]], Field(description="The number of CPU cores")
    ] = Range[int](min=2)
    memory: Annotated[
        Optional[Union[Range[Memory], float, int, str]],
        Field(description="The RAM size (e.g., 8GB)"),
    ] = Range[Memory](min="8GB")
    shm_size: Annotated[
        Optional[Union[Memory, float, int, str]],
        Field(
            description="The size of shared memory (e.g., 8GB). "
            "If you are using parallel communicating processes (e.g., dataloaders in PyTorch), "
            "you may need to configure this."
        ),
    ] = None
    gpu: Annotated[Optional[Union[GPU, int, str]], Field(description="The GPU resources")] = None
    disk: Annotated[
        Optional[Union[Disk, float, int, str]], Field(description="The disk resources")
    ] = None

    _force_type = validator("cpu", "memory", "shm_size", "gpu", "disk", allow_reuse=True)(
        force_type
    )
