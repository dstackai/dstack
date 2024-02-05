import re
from enum import Enum
from typing import List, Optional, Union

from pydantic import Field, confloat, root_validator, validator
from typing_extensions import Annotated, Literal

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import ForbidExtra

DEFAULT_RETRY_LIMIT = 3600


class SpotPolicy(str, Enum):
    SPOT = "spot"
    ONDEMAND = "on-demand"
    AUTO = "auto"


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
