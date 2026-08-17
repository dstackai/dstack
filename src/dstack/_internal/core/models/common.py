from enum import Enum
from typing import Any, Optional, TypeVar, Union, overload

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
)
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


def pop_null_field(values: Any, *path: str) -> Any:
    """
    Drop a field at `path` from the `values` nested dict if it's set to `null`.

    Mutates and returns the same `values` object.
    """
    if not isinstance(values, dict):
        return values
    node = values
    for key in path[:-1]:
        node = node.get(key)
        if not isinstance(node, dict):
            return values
    field = path[-1]
    if field in node and node[field] is None:
        del node[field]
    return values


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
