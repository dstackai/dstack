import re
from typing import Union

from pydantic import BaseModel, Extra


class ForbidExtra(BaseModel):
    class Config:
        extra = Extra.forbid


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
