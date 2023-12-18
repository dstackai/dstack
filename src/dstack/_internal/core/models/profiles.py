import re
from enum import Enum
from typing import List, Optional, Tuple, Union

from pydantic import Field, confloat, root_validator, validator
from typing_extensions import Annotated, Literal

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import ForbidExtra

DEFAULT_RETRY_LIMIT = 3600


class SpotPolicy(str, Enum):
    SPOT = "spot"
    ONDEMAND = "on-demand"
    AUTO = "auto"


def parse_memory(v: Optional[Union[int, str]]) -> Optional[int]:
    """
    Converts human-readable sizes (MB and GB) to megabytes
    >>> parse_memory("512MB")
    512
    >>> parse_memory("1 GB")
    1024
    """
    if v is None:
        return None
    if isinstance(v, str):
        m = re.fullmatch(r"(\d+) *([mg]b)?", v.strip().lower())
        if not m:
            raise ValueError(f"Invalid memory size: {v}")
        v = int(m.group(1))
        if m.group(2) == "gb":
            v = v * 1024
    return int(v)


def parse_duration(v: Optional[Union[int, str]]) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, int):
        return v
    regex = re.compile(r"(?P<amount>\d+) *(?P<unit>[smhdw])$")
    re_match = regex.match(v)
    if not re_match:
        raise ValueError(f"Cannot parse the duration {v}")
    amount, unit = int(re_match.group("amount")), re_match.group("unit")
    multiplier = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 24 * 3600,
        "w": 7 * 24 * 3600,
    }[unit]
    return amount * multiplier


def parse_max_duration(v: Union[int, str]) -> int:
    if v == "off":
        return v
    return parse_duration(v)


class ProfileGPU(ForbidExtra):
    name: Annotated[
        Optional[str],
        Field(description='The name of the GPU (e.g., "A100" or "H100")'),
    ]
    count: Annotated[
        int,
        Field(description="The minimum number of GPUs"),
    ] = 1
    memory: Annotated[
        Optional[Union[int, str]],
        Field(description='The minimum size of a single GPU memory (e.g., "16GB")'),
    ]
    total_memory: Annotated[
        Optional[Union[int, str]],
        Field(description='The minimum total size of all GPUs memory (e.g., "32GB")'),
    ]
    compute_capability: Annotated[
        Optional[Union[float, str, Tuple[int, int]]],
        Field(description="The minimum compute capability of the GPU (e.g., 7.5)"),
    ]
    _validate_mem = validator("memory", "total_memory", pre=True, allow_reuse=True)(parse_memory)

    @validator("name")
    def _validate_name(cls, name: Optional[str]) -> Optional[str]:
        if name is None:
            return None
        return name.upper()

    @validator("compute_capability", pre=True)
    def _validate_cc(
        cls, v: Optional[Union[float, str, Tuple[int, int]]]
    ) -> Optional[Tuple[int, int]]:
        if isinstance(v, float):
            v = str(v)
        if isinstance(v, str):
            m = re.fullmatch(r"(\d+)\.(\d+)", v)
            if not m:
                raise ValueError(f"Invalid compute capability: {v}")
            v = (int(m.group(1)), int(m.group(2)))
        return v


class ProfileDisk(ForbidExtra):
    size: Annotated[
        Optional[Union[int, str]],
        Field(description='The minimum size of disk (e.g., "100GB")'),
    ]
    _validate_size = validator("size", pre=True, allow_reuse=True)(parse_memory)


class ProfileResources(ForbidExtra):
    cpu: Annotated[Optional[int], Field(description="The minimum number of CPUs")] = 2
    memory: Annotated[
        Optional[Union[int, str]],
        Field(description='The minimum size of RAM memory (e.g., "16GB")'),
    ] = parse_memory("8GB")
    gpu: Annotated[
        Optional[Union[int, ProfileGPU]],
        Field(description="The minimum number of GPUs or a GPU spec"),
    ]
    shm_size: Annotated[
        Optional[Union[int, str]],
        Field(
            description='The size of shared memory (e.g., "8GB"). If you are using parallel communicating processes ('
            "e.g., dataloaders in PyTorch), you may need to configure this."
        ),
    ]
    disk: Annotated[
        Optional[Union[int, str, ProfileDisk]],
        Field(description="The minimum size of disk or a disk spec"),
    ] = ProfileDisk(size=parse_memory("100GB"))
    _validate_mem = validator("memory", "shm_size", pre=True, allow_reuse=True)(parse_memory)

    @validator("gpu", pre=True)
    def _validate_gpu(cls, v: Optional[Union[int, ProfileGPU]]) -> Optional[ProfileGPU]:
        if isinstance(v, int):
            v = ProfileGPU(count=v)
        return v

    @validator("disk", pre=True)
    def _validate_disk(cls, v: Optional[Union[int, str, ProfileDisk]]) -> Optional[ProfileDisk]:
        if isinstance(v, int):
            v = ProfileDisk(size=v)
        if isinstance(v, str):
            v = ProfileDisk(size=parse_memory(v))
        return v


class ProfileRetryPolicy(ForbidExtra):
    retry: Annotated[bool, Field(description="Whether to retry the run on failure or not")] = False
    limit: Annotated[
        Optional[Union[int, str]],
        Field(description="The maximum period of retrying the run, e.g., 4h or 1d"),
    ] = None

    _validate_limit = validator("limit", pre=True, allow_reuse=True)(parse_duration)

    @root_validator()
    @classmethod
    def _validate_fields(cls, field_values):
        if field_values["retry"] and "limit" not in field_values:
            field_values["limit"] = DEFAULT_RETRY_LIMIT
        if field_values.get("limit") is not None:
            field_values["retry"] = True
        return field_values


class Profile(ForbidExtra):
    name: Annotated[
        str,
        Field(
            description="The name of the profile that can be passed as `--profile` to `dstack run`"
        ),
    ]
    backends: Annotated[
        Optional[List[BackendType]],
        Field(description='The backends to consider for provisionig (e.g., "[aws, gcp]")'),
    ]
    resources: Annotated[
        ProfileResources,
        Field(description="The minimum resources of the instance to be provisioned"),
    ] = ProfileResources()
    spot_policy: Annotated[
        Optional[SpotPolicy],
        Field(
            description="The policy for provisioning spot or on-demand instances: spot, on-demand, or auto"
        ),
    ]
    retry_policy: Annotated[
        Optional[ProfileRetryPolicy], Field(description="The policy for re-submitting the run")
    ]
    max_duration: Annotated[
        Optional[Union[Literal["off"], str, int]],
        Field(
            description="The maximum duration of a run (e.g., 2h, 1d, etc). After it elapses, the run is forced to stop."
        ),
    ]
    max_price: Annotated[
        Optional[confloat(gt=0.0)], Field(description="The maximum price per hour, in dollars")
    ]
    default: Annotated[
        bool, Field(description="If set to true, `dstack run` will use this profile by default.")
    ] = False

    _validate_max_duration = validator("max_duration", pre=True, allow_reuse=True)(
        parse_max_duration
    )


class ProfilesConfig(ForbidExtra):
    profiles: List[Profile]

    class Config:
        schema_extra = {"$schema": "http://json-schema.org/draft-07/schema#"}

    def default(self) -> Profile:
        for p in self.profiles:
            if p.default:
                return p
        return Profile(name="default")

    def get(self, name: str) -> Profile:
        for p in self.profiles:
            if p.name == name:
                return p
        raise KeyError(name)
