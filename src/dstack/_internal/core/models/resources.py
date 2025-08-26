import math
from collections.abc import Mapping
from typing import Any, Dict, Generic, List, Optional, Tuple, TypeVar, Union

import gpuhunt
from pydantic import Field, parse_obj_as, root_validator, validator
from pydantic.generics import GenericModel
from typing_extensions import Annotated

from dstack._internal.core.models.common import CoreModel
from dstack._internal.utils.common import pretty_resources
from dstack._internal.utils.json_schema import add_extra_schema_types
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


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

    def intersect(self, other: "Range") -> Optional["Range"]:
        start = max(
            self.min if self.min is not None else -math.inf,
            other.min if other.min is not None else -math.inf,
        )
        end = min(
            self.max if self.max is not None else math.inf,
            other.max if other.max is not None else math.inf,
        )
        if start > end:
            return None
        return Range(
            min=start if abs(start) != math.inf else None,
            max=end if abs(end) != math.inf else None,
        )


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
DEFAULT_GPU_COUNT = Range[int](min=1)


class CPUSpec(CoreModel):
    arch: Annotated[
        Optional[gpuhunt.CPUArchitecture],
        Field(description="The CPU architecture, one of: `x86`, `arm`"),
    ] = None
    count: Annotated[Range[int], Field(description="The number of CPU cores")] = DEFAULT_CPU_COUNT

    class Config(CoreModel.Config):
        @staticmethod
        def schema_extra(schema: Dict[str, Any]):
            add_extra_schema_types(
                schema["properties"]["count"],
                extra_types=[{"type": "integer"}, {"type": "string"}],
            )

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
                    raise ValueError(f"CPU spec contains empty token: {v}")
                if ".." in token or token.isdigit():
                    if "count" in spec:
                        raise ValueError(f"CPU spec count conflict: {v}")
                    spec["count"] = token
                else:
                    try:
                        arch = gpuhunt.CPUArchitecture.cast(token)
                    except ValueError:
                        raise ValueError(f"Invalid CPU architecture: {v}")
                    if "arch" in spec:
                        raise ValueError(f"CPU spec arch conflict: {v}")
                    spec["arch"] = arch
            return spec
        # Range and min/max dict - for backward compatibility
        if isinstance(v, Range):
            return {"arch": None, "count": v}
        if isinstance(v, Mapping) and v.keys() == {"min", "max"}:
            return {"arch": None, "count": v}
        return v

    @validator("arch", pre=True)
    def _validate_arch(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, gpuhunt.CPUArchitecture):
            return v
        if isinstance(v, str):
            return gpuhunt.CPUArchitecture.cast(v)
        return v


class GPUSpec(CoreModel):
    vendor: Annotated[
        Optional[gpuhunt.AcceleratorVendor],
        Field(
            description="The vendor of the GPU/accelerator, one of: `nvidia`, `amd`, `google` (alias: `tpu`), `intel`"
        ),
    ] = None
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

    class Config(CoreModel.Config):
        @staticmethod
        def schema_extra(schema: Dict[str, Any]):
            add_extra_schema_types(
                schema["properties"]["count"],
                extra_types=[{"type": "integer"}, {"type": "string"}],
            )
            add_extra_schema_types(
                schema["properties"]["name"],
                extra_types=[{"type": "string"}],
            )
            add_extra_schema_types(
                schema["properties"]["memory"],
                extra_types=[{"type": "integer"}, {"type": "string"}],
            )
            add_extra_schema_types(
                schema["properties"]["total_memory"],
                extra_types=[{"type": "integer"}, {"type": "string"}],
            )

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
                try:
                    vendor = cls._vendor_from_string(token)
                except ValueError:
                    vendor = None
                if vendor:
                    if "vendor" in spec:
                        raise ValueError(f"GPU spec vendor conflict: {v}")
                    spec["vendor"] = vendor
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
        if v is None:
            return None
        if not isinstance(v, list):
            v = [v]
        validated: List[Any] = []
        has_tpu_prefix = False
        for name in v:
            if isinstance(name, str) and name.startswith("tpu-"):
                name = name[4:]
                has_tpu_prefix = True
            validated.append(name)
        if has_tpu_prefix:
            logger.warning("`tpu-` prefix is deprecated, specify gpu_vendor instead")
        return validated

    @validator("vendor", pre=True)
    def _validate_vendor(
        cls, v: Union[str, gpuhunt.AcceleratorVendor, None]
    ) -> Optional[gpuhunt.AcceleratorVendor]:
        if v is None:
            return None
        if isinstance(v, gpuhunt.AcceleratorVendor):
            return v
        if isinstance(v, str):
            return cls._vendor_from_string(v)
        raise TypeError(f"Unsupported type: {v!r}")

    @classmethod
    def _vendor_from_string(cls, v: str) -> gpuhunt.AcceleratorVendor:
        v = v.lower()
        if v == "tpu":
            return gpuhunt.AcceleratorVendor.GOOGLE
        if v == "tt":
            return gpuhunt.AcceleratorVendor.TENSTORRENT
        return gpuhunt.AcceleratorVendor.cast(v)


class DiskSpec(CoreModel):
    size: Annotated[Range[Memory], Field(description="Disk size")]

    class Config(CoreModel.Config):
        @staticmethod
        def schema_extra(schema: Dict[str, Any]):
            add_extra_schema_types(
                schema["properties"]["size"],
                extra_types=[{"type": "integer"}, {"type": "string"}],
            )

    @classmethod
    def __get_validators__(cls):
        yield cls._parse
        yield cls.validate

    @classmethod
    def _parse(cls, v: Any) -> Any:
        if isinstance(v, (str, int, float)):
            return {"size": v}
        return v


DEFAULT_DISK = DiskSpec(size=Range[Memory](min=Memory.parse("100GB"), max=None))


class ResourcesSpec(CoreModel):
    # TODO: Remove Range[int] in 0.20. Range[int] for backward compatibility only.
    cpu: Annotated[Union[CPUSpec, Range[int]], Field(description="The CPU requirements")] = (
        CPUSpec()
    )
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

    class Config(CoreModel.Config):
        @staticmethod
        def schema_extra(schema: Dict[str, Any]):
            add_extra_schema_types(
                schema["properties"]["cpu"],
                extra_types=[{"type": "integer"}, {"type": "string"}],
            )
            add_extra_schema_types(
                schema["properties"]["memory"],
                extra_types=[{"type": "integer"}, {"type": "string"}],
            )
            add_extra_schema_types(
                schema["properties"]["shm_size"],
                extra_types=[{"type": "integer"}, {"type": "string"}],
            )
            add_extra_schema_types(
                schema["properties"]["gpu"],
                extra_types=[{"type": "integer"}, {"type": "string"}],
            )
            add_extra_schema_types(
                schema["properties"]["disk"],
                extra_types=[{"type": "integer"}, {"type": "string"}],
            )

    def pretty_format(self) -> str:
        # TODO: Remove in 0.20. Use self.cpu directly
        cpu = parse_obj_as(CPUSpec, self.cpu)
        resources: Dict[str, Any] = dict(cpu_arch=cpu.arch, cpus=cpu.count, memory=self.memory)
        if self.gpu:
            gpu = self.gpu
            resources.update(
                gpu_name=",".join(gpu.name) if gpu.name else None,
                gpu_count=gpu.count,
                gpu_memory=gpu.memory,
                total_gpu_memory=gpu.total_memory,
                compute_capability=gpu.compute_capability,
            )
        if self.disk:
            resources.update(disk_size=self.disk.size)
        res = pretty_resources(**resources)
        return res

    def dict(self, *args, **kwargs) -> Dict:
        # super() does not work with pydantic-duality
        res = CoreModel.dict(self, *args, **kwargs)
        self._update_serialized_cpu(res)
        return res

    # TODO: Remove in 0.20. Added for backward compatibility.
    def _update_serialized_cpu(self, values: Dict):
        cpu = values["cpu"]
        if cpu:
            arch = cpu.get("arch")
            count = cpu.get("count")
            if count and arch in [None, gpuhunt.CPUArchitecture.X86.value]:
                values["cpu"] = count
