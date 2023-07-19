import re
from typing import List, Optional, Union

from pydantic import validator

from dstack._internal.core.configuration import ForbidExtra
from dstack._internal.core.job import SpotPolicy

DEFAULT_CPU = 2
DEFAULT_MEM = "8GB"
DEFAULT_RETRY_LIMIT = 3600


def parse_memory(v: Optional[Union[int, str]]) -> Optional[int]:
    """
    Converts human-readable sizes (MB and GB) to megabytes
    >>> parse_memory("512MB")
    512
    >>> parse_memory("1 GB")
    1024
    """
    if isinstance(v, str):
        m = re.fullmatch(r"(\d+) *([mg]b)?", v.strip().lower())
        if not m:
            raise ValueError(f"Invalid memory size: {v}")
        v = int(m.group(1))
        if m.group(2) == "gb":
            v = v * 1024
    return int(v)


def parse_duration(v: Union[int, str]) -> int:
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
        return -1
    return parse_duration(v)


class ProfileGPU(ForbidExtra):
    name: Optional[str]
    count: int = 1
    memory: Optional[Union[int, str]]
    _validate_mem = validator("memory", pre=True, allow_reuse=True)(parse_memory)


class ProfileResources(ForbidExtra):
    gpu: Optional[Union[int, ProfileGPU]]
    memory: Union[int, str] = parse_memory(DEFAULT_MEM)
    shm_size: Optional[Union[int, str]]
    cpu: int = DEFAULT_CPU
    _validate_mem = validator("memory", "shm_size", pre=True, allow_reuse=True)(parse_memory)

    @validator("gpu", pre=True)
    def _validate_gpu(cls, v: Optional[Union[int, ProfileGPU]]) -> Optional[ProfileGPU]:
        if isinstance(v, int):
            v = ProfileGPU(count=v)
        return v


class ProfileRetryPolicy(ForbidExtra):
    retry: bool = False
    limit: Union[int, str] = DEFAULT_RETRY_LIMIT
    _validate_limit = validator("limit", pre=True, allow_reuse=True)(parse_duration)


class Profile(ForbidExtra):
    name: str
    project: Optional[str]
    resources: ProfileResources = ProfileResources()
    spot_policy: Optional[SpotPolicy]
    retry_policy: ProfileRetryPolicy = ProfileRetryPolicy()
    max_duration: Optional[Union[int, str]]
    default: bool = False
    _validate_max_duration = validator("max_duration", pre=True, allow_reuse=True)(
        parse_max_duration
    )


class ProfilesConfig(ForbidExtra):
    profiles: List[Profile]

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
