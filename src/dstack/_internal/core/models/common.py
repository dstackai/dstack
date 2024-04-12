import re
from typing import Union

from pydantic_duality import DualBaseModel, DualBaseModelMeta


# Change DualBaseModelMeta so that model parsed with MyModel.__response__
# would pass the check for isinstance(instance, MyModel).
class CoreModelMeta(DualBaseModelMeta):
    """Metaclass used for custom types."""

    def __instancecheck__(cls, instance) -> bool:
        return (
            type.__instancecheck__(cls, instance)
            or isinstance(instance, cls.__request__)
            or isinstance(instance, cls.__response__)
        )

    def __subclasscheck__(cls, subclass: type):
        return (
            type.__subclasscheck__(cls, subclass)
            or issubclass(subclass, cls.__request__)
            or issubclass(subclass, cls.__response__)
        )


# DualBaseModel creates two classes for the model:
# one with extra = "forbid" (CoreModel/CoreModel.__request__),
# and another with extra = "ignore" (CoreModel.__response__).
# This allows to use the same model both for a strict parsing of the user input and
# for a permissive parsing of the server responses.


class CoreModel(DualBaseModel, metaclass=CoreModelMeta):
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
