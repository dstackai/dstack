import re
from typing import Any, Optional, Union

from pydantic import BeforeValidator, GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, core_schema
from typing_extensions import Annotated, Literal, overload


class Duration(int):
    """
    Duration in seconds.
    """

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

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls.parse,
            serialization=core_schema.plain_serializer_function_ser_schema(
                int, return_schema=core_schema.int_schema()
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        # A duration is accepted either as a number of seconds or as a shorthand string
        # like `2h`, but it always serializes as a number of seconds.
        if handler.mode == "validation":
            return {"anyOf": [{"type": "integer"}, {"type": "string"}]}
        return {"type": "integer"}


@overload
def parse_duration(v: None) -> None: ...


@overload
def parse_duration(v: Union[int, str]) -> int: ...


def parse_duration(v: Optional[Union[int, str]]) -> Optional[int]:
    if v is None:
        return None
    return Duration.parse(v)


def parse_off_duration(v: Optional[Union[int, str, bool]]) -> Optional[Union[Literal["off"], int]]:
    if v == "off" or v is False:
        return "off"
    if v is True or v is None:
        return None
    duration = parse_duration(v)
    if duration < 0:
        raise ValueError("Duration cannot be negative")
    return duration


def parse_idle_duration(v: Optional[Union[int, str, bool]]) -> Optional[int]:
    # Differs from `parse_off_duration` to accept negative durations as `off`
    # for backward compatibility.
    if v == "off" or v is False or v == -1:
        return -1
    if v is True:
        return None
    return parse_duration(v)


# Both include `None` in their own value domain rather than being wrapped in `Optional[...]` at the
# field, which is why the names say so. `None` means "unspecified, use the default" and `true` is the
# documented way to ask for it, so it belongs to the domain. It is also required mechanically: a
# `BeforeValidator` nested inside an `Optional[...]` runs *after* the nullable check, so the `None`
# it returns for `true` would then be rejected by the inner union. Use plain `Duration` for a
# duration that is required.
#
# The parsed value is `int`, not `Duration`, even though the parse functions return `Duration`,
# because code may assign non-`Duration` values directly. Switching to `Duration` would fail serialization in such cases.

OptionalOffableDuration = Annotated[
    Optional[Union[Literal["off"], int]],
    BeforeValidator(parse_off_duration, json_schema_input_type=Optional[Union[int, str, bool]]),
]
"""
A duration that can be switched off. Value domain: `None` (unspecified), `"off"`, or seconds.

`false` and `"off"` both normalize to `"off"`; `true` and omission both normalize to `None`.
Negative values are rejected — contrast `OptionalIdleDuration`.
"""

OptionalIdleDuration = Annotated[
    Optional[int],
    BeforeValidator(
        parse_idle_duration,
        json_schema_input_type=Optional[Union[Literal["off"], int, str, bool]],
    ),
]
"""
A duration whose "off" state is the sentinel `-1` rather than a string.

`false`, `"off"` and `-1` all normalize to `-1`, and any negative value is accepted and left as
is. That is deliberate and load-bearing: `-1` is what older clients and existing stored rows use
to mean "off", so rejecting negatives here would break reads of data already in the database.
"""
