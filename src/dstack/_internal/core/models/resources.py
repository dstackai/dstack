import math
from collections.abc import Mapping
from typing import Any, Dict, Generic, List, Optional, Tuple, TypeVar, Union

import gpuhunt
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetCoreSchemaHandler,
    GetJsonSchemaHandler,
    SerializerFunctionWrapHandler,
    Tag,
    field_validator,
    model_serializer,
    model_validator,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, core_schema
from typing_extensions import Annotated

from dstack._internal.core.models.common import CoreModel
from dstack._internal.utils.common import pretty_resources
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


T = TypeVar("T", bound=Union[int, float])

# The shorthand forms these types accept in addition to their declared shape. Declared on the
# type so that every field using it reports the same thing in the generated JSON Schema, instead
# of each field restating it in a sibling config class.
_INT_OR_STR_INPUT = [core_schema.int_schema(), core_schema.str_schema()]


class Range(BaseModel, Generic[T]):
    model_config = ConfigDict(extra="forbid")

    min: Optional[T] = None
    max: Optional[T] = None

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        model_schema = handler(source_type)
        return core_schema.no_info_before_validator_function(
            cls._parse,
            model_schema,
            # A range is also written as `8`, `2..8`, or `16GB..`.
            json_schema_input_schema=core_schema.union_schema([model_schema, *_INT_OR_STR_INPUT]),
        )

    @classmethod
    def _parse(cls, v: Any) -> Any:
        if isinstance(v, str) and ".." in v:
            v = v.replace(" ", "")
            min, max = v.split("..")
            return dict(min=min or None, max=max or None)
        if isinstance(v, (str, int, float)):
            return dict(min=v, max=v)
        return v

    @model_validator(mode="after")
    def _post_validate(self) -> "Range[T]":
        if self.min is None and self.max is None:
            raise ValueError("Invalid empty range: ..")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"Invalid range order: {self.min}..{self.max}")
        return self

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

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls.parse,
            serialization=core_schema.plain_serializer_function_ser_schema(
                float, return_schema=core_schema.float_schema()
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        # A memory size is accepted as a number of gigabytes or as `16GB`/`512MB`/`1TB`,
        # and always serializes as a number of gigabytes.
        if handler.mode == "validation":
            return {"anyOf": [{"type": "number"}, {"type": "integer"}, {"type": "string"}]}
        return {"type": "number"}


class ComputeCapability(Tuple[int, int]):
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

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls.validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                list, return_schema=core_schema.list_schema(core_schema.int_schema())
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        serialized = {"type": "array", "items": {"type": "integer"}}
        if handler.mode == "validation":
            # Written as `7.5` (a YAML float), as `"7.5"`, or as a two-element sequence.
            return {"anyOf": [{"type": "number"}, {"type": "string"}, serialized]}
        return serialized


DEFAULT_CPU_COUNT = Range[int](min=2)
DEFAULT_MEMORY_SIZE = Range[Memory](min=Memory.parse("8GB"))
DEFAULT_GPU_COUNT = Range[int](min=1)


class CPUSpec(CoreModel):
    arch: Annotated[
        Optional[gpuhunt.CPUArchitecture],
        Field(description="The CPU architecture, one of: `x86`, `arm`"),
    ] = None
    count: Annotated[Range[int], Field(description="The number of CPU cores")] = DEFAULT_CPU_COUNT

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        model_schema = handler(source_type)
        return core_schema.no_info_before_validator_function(
            cls.parse,
            model_schema,
            # Also written as a count (`8`) or a `<arch>:<count>` shorthand (`arm:8`).
            json_schema_input_schema=core_schema.union_schema([model_schema, *_INT_OR_STR_INPUT]),
        )

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
        # A subset rather than exactly {"min", "max"}: `ResourcesSpec` serializes `cpu` down to its
        # count for old clients, and under `exclude_none=True` that leaves just `{"min": ...}`.
        # Requiring both keys made the round trip land on the `Range[int]` arm of `ResourcesSpec.cpu`
        # instead of coming back as a `CPUSpec`. `arch`/`count` are the only `CPUSpec` fields, so a
        # mapping of min/max is unambiguously a range.
        if isinstance(v, Mapping) and v and v.keys() <= {"min", "max"}:
            return {"arch": None, "count": v}
        return v

    @field_validator("arch", mode="before")
    @classmethod
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

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        model_schema = handler(source_type)
        return core_schema.no_info_before_validator_function(
            cls.parse,
            model_schema,
            # Also written as a count (`8`) or a `:`-separated shorthand (`A100:8`, `nvidia:16GB`).
            json_schema_input_schema=core_schema.union_schema([model_schema, *_INT_OR_STR_INPUT]),
        )

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

    @field_validator("name", mode="before", json_schema_input_type=Optional[Union[List[str], str]])
    @classmethod
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

    @field_validator("vendor", mode="before")
    @classmethod
    def _validate_vendor(
        cls, v: Union[str, gpuhunt.AcceleratorVendor, None]
    ) -> Optional[gpuhunt.AcceleratorVendor]:
        if v is None:
            return None
        if isinstance(v, gpuhunt.AcceleratorVendor):
            return v
        if isinstance(v, str):
            return cls._vendor_from_string(v)
        # A TypeError raised inside a validator is no longer converted to a ValidationError
        # in pydantic v2, so it would escape as a 500 instead of a 422.
        raise ValueError(f"Unsupported type: {v!r}")

    @classmethod
    def _vendor_from_string(cls, v: str) -> gpuhunt.AcceleratorVendor:
        v = v.lower()
        if v == "tpu":
            return gpuhunt.AcceleratorVendor.GOOGLE
        if v == "tt":
            return gpuhunt.AcceleratorVendor.TENSTORRENT
        return gpuhunt.AcceleratorVendor.cast(v)


DEFAULT_GPU_SPEC = GPUSpec(count=Range[int](min=0, max=None))


class DiskSpec(CoreModel):
    size: Annotated[Range[Memory], Field(description="Disk size")]

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        model_schema = handler(source_type)
        return core_schema.no_info_before_validator_function(
            cls._parse,
            model_schema,
            # Also written as a bare size (`100GB`).
            json_schema_input_schema=core_schema.union_schema([model_schema, *_INT_OR_STR_INPUT]),
        )

    @classmethod
    def _parse(cls, v: Any) -> Any:
        if isinstance(v, (str, int, float)):
            return {"size": v}
        return v


DEFAULT_DISK = DiskSpec(size=Range[Memory](min=Memory.parse("100GB"), max=None))


class ResourcesSpec(CoreModel):
    # TODO: remove `Range[int]` in 0.20. It is kept only for backward compatibility.
    cpu: Annotated[
        Union[
            # `Tag` only names the arm in validation errors. Without it the `loc` of a bad `cpu`
            # spells out the whole wrapped schema —
            # `cpu.function-before[parse(), function-before[parse(), ... CPUSpec]].count` — which
            # is what `dstack apply` shows the user.
            Annotated[CPUSpec, Tag("CPUSpec")],
            Annotated[Range[int], Tag("Range[int]")],
        ],
        # `CPUSpec` and `Range[int]` both accept a bare int/str, so the arm has to be picked by
        # declaration order rather than by pydantic v2's "smart" union resolution.
        Field(description="The CPU requirements", union_mode="left_to_right"),
    ] = CPUSpec()
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
    gpu: Annotated[Optional[GPUSpec], Field(description="The GPU requirements")] = DEFAULT_GPU_SPEC
    """`gpu` is optional for backward compatibility."""
    disk: Annotated[Optional[DiskSpec], Field(description="The disk resources")] = DEFAULT_DISK

    @classmethod
    def unconstrained(cls) -> "ResourcesSpec":
        """ResourcesSpec with no meaningful minimum constraints."""
        return cls(
            cpu=CPUSpec(count=Range[int](min=1, max=None)),
            memory=Range[Memory](min=Memory.parse("0"), max=None),
            gpu=DEFAULT_GPU_SPEC,
            disk=None,
        )

    def pretty_format(self) -> str:
        # TODO: Remove in 0.20. Use self.cpu directly
        cpu = CPUSpec.model_validate(self.cpu)
        resources: Dict[str, Any] = dict(cpu_arch=cpu.arch, cpus=cpu.count, memory=self.memory)
        if self.gpu:
            gpu = self.gpu
            resources.update(
                gpu_vendor=gpu.vendor,
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

    @model_serializer(mode="wrap")
    def _serialize(self, handler: SerializerFunctionWrapHandler) -> Dict[str, Any]:
        res = handler(self)
        self._update_serialized_cpu(res)
        return res

    # TODO: Remove in 0.20. Added for backward compatibility.
    def _update_serialized_cpu(self, values: Dict):
        cpu = values.get("cpu")
        if cpu:
            arch = cpu.get("arch")
            count = cpu.get("count")
            if count and arch in [None, gpuhunt.CPUArchitecture.X86.value]:
                values["cpu"] = count
