import re
from enum import Enum
from typing import Any, Callable, Optional, Union

import orjson
from pydantic import Field
from pydantic_duality import DualBaseModel
from typing_extensions import Annotated

from dstack._internal.utils.json_utils import pydantic_orjson_dumps

IncludeExcludeFieldType = Union[int, str]
IncludeExcludeSetType = set[IncludeExcludeFieldType]
IncludeExcludeDictType = dict[
    IncludeExcludeFieldType, Union[bool, IncludeExcludeSetType, "IncludeExcludeDictType"]
]
IncludeExcludeType = Union[IncludeExcludeSetType, IncludeExcludeDictType]


# DualBaseModel creates two classes for the model:
# one with extra = "forbid" (CoreModel/CoreModel.__request__),
# and another with extra = "ignore" (CoreModel.__response__).
# This allows to use the same model both for a strict parsing of the user input and
# for a permissive parsing of the server responses.
class CoreModel(DualBaseModel):
    class Config:
        json_loads = orjson.loads
        json_dumps = pydantic_orjson_dumps

    def json(
        self,
        *,
        include: Optional[IncludeExcludeType] = None,
        exclude: Optional[IncludeExcludeType] = None,
        by_alias: bool = False,
        skip_defaults: Optional[bool] = None,  # ignore as it's deprecated
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
        encoder: Optional[Callable[[Any], Any]] = None,
        models_as_dict: bool = True,  # does not seems to be needed by dstack or dependencies
        **dumps_kwargs: Any,
    ) -> str:
        """
        Override `json()` method so that it calls `dict()`.
        Allows changing how models are serialized by overriding `dict()` only.
        By default, `json()` won't call `dict()`, so changes applied in `dict()` won't take place.
        """
        data = self.dict(
            by_alias=by_alias,
            include=include,
            exclude=exclude,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
        )
        if self.__custom_root_type__:
            data = data["__root__"]
        return self.__config__.json_dumps(data, default=encoder, **dumps_kwargs)


class Duration(int):
    """
    Duration in seconds.
    """

    @classmethod
    def __get_validators__(cls):
        yield cls.parse

    @classmethod
    def parse(cls, v: Union[int, str]) -> "Duration":
        if isinstance(v, (int, float)):
            return cls(v)
        if isinstance(v, str):
            try:
                return cls(int(v))
            except ValueError:
                pass
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
            return cls(amount * multiplier)
        raise ValueError(f"Cannot parse the duration {v}")


class RegistryAuth(CoreModel):
    """
    Credentials for pulling a private Docker image.

    Attributes:
        username (str): The username
        password (str): The password or access token
    """

    username: Annotated[str, Field(description="The username")]
    password: Annotated[str, Field(description="The password or access token")]

    class Config(CoreModel.Config):
        frozen = True


class ApplyAction(str, Enum):
    CREATE = "create"  # resource is to be created or overridden
    UPDATE = "update"  # resource is to be updated in-place


class NetworkMode(str, Enum):
    HOST = "host"
    BRIDGE = "bridge"
