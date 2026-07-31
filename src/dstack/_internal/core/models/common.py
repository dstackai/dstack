import re
from enum import Enum
from typing import Any, Optional, TypeVar, Union, overload

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetCoreSchemaHandler,
    GetJsonSchemaHandler,
    TypeAdapter,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, core_schema
from typing_extensions import Annotated

# pydantic v2 generates draft 2020-12. The published `configuration.json` / `profiles.json`
# advertise the dialect they were generated for, so this has to move with pydantic.
JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


def drop_merged_profile(schema: dict[str, Any]) -> None:
    """
    `json_schema_extra` hook for the specs carrying a `merged_profile`.

    It is an internal field computed from the configuration and the profile, never written by a
    user, so it must not appear in the published schema.
    """
    schema.get("properties", {}).pop("merged_profile", None)


# Mirrors pydantic v2's `IncEx`, so these can be passed straight to `model_dump`/`model_copy`.
# v2 keys a mapping by int or str but not both, and its values are `IncEx | bool`.
IncludeExcludeFieldType = Union[int, str]
IncludeExcludeSetType = Union[set[int], set[str]]
# `dict` rather than `Mapping`, so these stay assignable both *to* pydantic's `IncEx` and to the
# plain `Dict` parameters the plugin API declares. Keyed by int or str but not both, like `IncEx`.
IncludeExcludeDictType = Union[
    dict[int, Union["IncludeExcludeType", bool]],
    dict[str, Union["IncludeExcludeType", bool]],
]
IncludeExcludeType = Union[IncludeExcludeSetType, IncludeExcludeDictType]


class CoreModel(BaseModel):
    """
    The base class for all dstack models.

    Unknown fields are rejected, which is what makes `dstack apply` report a typo'd key in a
    user's YAML and what makes the API reject an unexpected request body. Reading a stored blob
    or a peer's response needs the opposite — see `validate_extra_ignore` below.
    """

    model_config = ConfigDict(
        extra="forbid",
        # YAML numbers reach str fields as int/float, e.g. a `python: 3.10` style shorthand.
        coerce_numbers_to_str=True,
    )


class FrozenCoreModel(CoreModel):
    model_config = ConfigDict(frozen=True)


T = TypeVar("T")

_type_adapters: dict[Any, TypeAdapter] = {}


@overload
def validate_extra_ignore(tp: type[T], obj: Any) -> T: ...


@overload
def validate_extra_ignore(tp: Any, obj: Any) -> Any: ...


def validate_extra_ignore(tp: Any, obj: Any) -> Any:
    """
    Validate `obj` against `tp` with `extra="ignore"`, dropping unknown fields at every level.

    This is the read path: anything decoded from a stored blob or from a peer's response goes
    through here, so that a newer writer adding a field does not break an older reader.

    `obj` may be an instance of a *different* model class, which is how the backend configurators
    re-read an `AWSBackendConfigWithCreds` as an `AWSConfig`. v1's `parse_obj` accepted that
    directly; v2 needs a dict, so dump first.
    """
    if isinstance(obj, BaseModel):
        obj = obj.model_dump()
    return _get_type_adapter(tp).validate_python(obj, extra="ignore")


@overload
def validate_json_extra_ignore(tp: type[T], data: Union[str, bytes]) -> T: ...


@overload
def validate_json_extra_ignore(tp: Any, data: Union[str, bytes]) -> Any: ...


def validate_json_extra_ignore(tp: Any, data: Union[str, bytes]) -> Any:
    """
    The JSON-input counterpart of `validate_extra_ignore`, keeping native JSON parsing rather
    than going through `json.loads` and then validating in Python mode.
    """
    return _get_type_adapter(tp).validate_json(data, extra="ignore")


def _get_type_adapter(tp: Any) -> TypeAdapter:
    # Constructing a TypeAdapter builds a schema and a validator, so reuse them per type.
    try:
        adapter = _type_adapters.get(tp)
    except TypeError:
        # An unhashable annotation cannot be cached. Rare enough not to matter.
        return TypeAdapter(tp)
    if adapter is None:
        adapter = TypeAdapter(tp)
        _type_adapters[tp] = adapter
    return adapter


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


class RegistryAuth(FrozenCoreModel):
    """
    Credentials for pulling a private Docker image.

    Attributes:
        username (str): The username
        password (str): The password or access token
    """

    username: Annotated[str, Field(description="The username")]
    password: Annotated[str, Field(description="The password or access token")]


class ApplyAction(str, Enum):
    CREATE = "create"
    """`CREATE` means the resource is to be created or overridden."""
    UPDATE = "update"
    """`UPDATE` means the resource is to be updated in-place."""


class NetworkMode(str, Enum):
    HOST = "host"
    BRIDGE = "bridge"


class EntityReference(CoreModel):
    """
    Cross-project entity reference.
    """

    project: Annotated[
        Optional[str],
        Field(description="The project name. If unspecified, refers to the current project"),
    ] = None
    name: Annotated[str, Field(description="The entity name")]

    @classmethod
    def parse(cls, v: Union[str, "EntityReference"]) -> "EntityReference":
        if isinstance(v, EntityReference):
            return v
        invalid_ref_error = ValueError(
            "Invalid entity reference. Only `<name>` or `<project>/<name>` formats are allowed"
        )
        parts = v.split("/")
        if any(len(part) == 0 for part in parts):
            raise invalid_ref_error
        if len(parts) == 1:
            return cls(project=None, name=parts[0])
        if len(parts) == 2:
            return cls(project=parts[0], name=parts[1])
        raise invalid_ref_error

    def format(self) -> str:
        if self.project is None:
            return self.name
        return f"{self.project}/{self.name}"
