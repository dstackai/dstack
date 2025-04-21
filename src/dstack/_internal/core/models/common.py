import re
from enum import Enum
from typing import Union

from pydantic import Field
from pydantic_duality import DualBaseModel
from typing_extensions import Annotated


# DualBaseModel creates two classes for the model:
# one with extra = "forbid" (CoreModel/CoreModel.__request__),
# and another with extra = "ignore" (CoreModel.__response__).
# This allows to use the same model both for a strict parsing of the user input and
# for a permissive parsing of the server responses.
class CoreModel(DualBaseModel):
    pass


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

    class Config:
        frozen = True

    username: Annotated[str, Field(description="The username")]
    password: Annotated[str, Field(description="The password or access token")]


class ApplyAction(str, Enum):
    CREATE = "create"  # resource is to be created or overridden
    UPDATE = "update"  # resource is to be updated in-place


class NetworkMode(str, Enum):
    HOST = "host"
    BRIDGE = "bridge"
