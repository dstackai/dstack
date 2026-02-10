"""
Generates schema reference for dstack models.
"""

import importlib
import inspect
import logging
import re
from enum import Enum
from fnmatch import fnmatch

import mkdocs_gen_files
import yaml
from mkdocs.structure.files import File
from pydantic.main import BaseModel
from typing_extensions import Annotated, Any, Dict, Literal, Type, Union, get_args, get_origin

from dstack._internal.core.models.resources import Range

FILE_PATTERN = "docs/reference/**.md"
logger = logging.getLogger("mkdocs.plugins.dstack.schema")

logger.info("Generating schema reference...")


def _is_linkable_type(annotation: Any) -> bool:
    """Check if a type annotation contains a BaseModel subclass (excluding Range)."""
    if inspect.isclass(annotation):
        return issubclass(annotation, BaseModel) and not issubclass(annotation, Range)
    origin = get_origin(annotation)
    if origin is Annotated:
        return _is_linkable_type(get_args(annotation)[0])
    if origin is Union:
        return any(_is_linkable_type(arg) for arg in get_args(annotation))
    if origin is list:
        args = get_args(annotation)
        return bool(args) and _is_linkable_type(args[0])
    return False


def _type_sort_key(t: str) -> tuple:
    """Sort key for type parts: primitives first, then literals, then compound types."""
    order = {"bool": 0, "int": 1, "float": 2, "str": 3}
    if t in order:
        return (0, order[t])
    if t.startswith('"'):
        return (1, t)
    if t.startswith("list"):
        return (2, t)
    if t == "dict":
        return (3, "")
    if t == "object":
        return (4, "")
    return (5, t)


def get_friendly_type(annotation: Type) -> str:
    """Get a user-friendly type string for documentation.

    Produces types like: ``int | str``, ``"rps"``, ``list[object]``, ``"spot" | "on-demand" | "auto"``.
    """
    # Unwrap Annotated
    if get_origin(annotation) is Annotated:
        return get_friendly_type(get_args(annotation)[0])

    # Handle Union (including Optional)
    if get_origin(annotation) is Union:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if not args:
            return ""
        parts: list = []
        for arg in args:
            friendly = get_friendly_type(arg)
            # Split compound types (e.g., "int | str" from Range) to deduplicate,
            # but avoid splitting types that contain brackets (e.g., list[...])
            if "[" not in friendly:
                for part in friendly.split(" | "):
                    if part and part not in parts:
                        parts.append(part)
            else:
                if friendly and friendly not in parts:
                    parts.append(friendly)
        parts.sort(key=_type_sort_key)
        return " | ".join(parts)

    # Handle Literal — show quoted values
    if get_origin(annotation) is Literal:
        values = get_args(annotation)
        return " | ".join(f'"{v}"' for v in values)

    # Handle list
    if get_origin(annotation) is list:
        args = get_args(annotation)
        if args:
            inner = get_friendly_type(args[0])
            # Simplify lists of enum/literal values to list[str]
            if inner.startswith('"') and " | " in inner:
                inner = "str"
            return f"list[{inner}]"
        return "list"

    # Handle dict
    if get_origin(annotation) is dict:
        return "dict"

    # Handle concrete classes
    if inspect.isclass(annotation):
        # Enum — show quoted values
        if issubclass(annotation, Enum):
            values = [e.value for e in annotation]
            return " | ".join(f'"{v}"' for v in values)

        # Range — depends on inner type parameter
        if issubclass(annotation, Range):
            min_field = annotation.__fields__.get("min")
            if min_field and inspect.isclass(min_field.type_):
                # Range[Memory] → str, Range[int] → int | str
                if issubclass(min_field.type_, float):
                    return "str"
            return "int | str"

        # Memory (float subclass that parses "8GB" strings)
        from dstack._internal.core.models.resources import Memory as _Memory

        if issubclass(annotation, _Memory):
            return "str"

        # BaseModel subclass (not Range)
        if issubclass(annotation, BaseModel) and not issubclass(annotation, Range):
            # Root models (with __root__ field) — resolve from the root type
            if "__root__" in annotation.__fields__:
                return get_friendly_type(annotation.__fields__["__root__"].annotation)
            # Models with custom __get_validators__ accept primitive input (int, str)
            # in addition to the full object form (e.g., GPUSpec, CPUSpec, DiskSpec)
            if "__get_validators__" in annotation.__dict__:
                return "int | str | object"
            return "object"

        # ComputeCapability (tuple subclass that parses "7.5" strings)
        if annotation.__name__ == "ComputeCapability":
            return "float | str"

        # Constrained and primitive types — check MRO
        # bool must come before int (bool is a subclass of int)
        if issubclass(annotation, bool):
            return "bool"
        if issubclass(annotation, int):
            # Duration (int subclass that parses "5m" strings)
            if annotation.__name__ == "Duration":
                return "int | str"
            return "int"
        if issubclass(annotation, float):
            return "float"
        if issubclass(annotation, str):
            return "str"
        if issubclass(annotation, (list, tuple)):
            return "list"
        if issubclass(annotation, dict):
            return "dict"

        return annotation.__name__

    return str(annotation)


def generate_schema_reference(
    model_path: str,
    *,
    overrides: Dict[str, Dict[str, Any]] = None,
    prefix: str = "",
) -> str:
    module, model_name = model_path.rsplit(".", maxsplit=1)
    cls = getattr(importlib.import_module(module), model_name)
    rows = []
    if (
        not overrides
        or "show_root_heading" not in overrides
        or overrides.get("show_root_heading") is True
    ):
        rows.extend(
            [
                prefix + f"### {cls.__name__}",
                "",
            ]
        )
    for name, field in cls.__fields__.items():
        default = field.default
        if isinstance(default, Enum):
            default = default.value
        values = dict(
            name=name,
            description=field.field_info.description,
            type=get_friendly_type(field.annotation),
            default=default,
            required=field.required,
        )
        # TODO: If the field doesn't have description (e.g. BaseConfiguration.type), we could fallback to docstring
        if values["description"]:
            if overrides and name in overrides:
                values.update(overrides[name])
            field_type = next(iter(get_args(field.annotation)), None)
            # TODO: This is a dirty workaround
            if field_type:
                if field.annotation.__name__ == "Annotated":
                    if field_type.__name__ in ["Optional", "List", "list", "Union"]:
                        field_type = get_args(field_type)[0]
                base_model = _is_linkable_type(field_type)
            else:
                base_model = False
            _defaults = (
                f"Defaults to `{values['default']}`."
                if not base_model and values.get("default")
                else ""
            )
            _must_be = (
                f"Must be `{values['default']}`."
                if not base_model and values.get("default")
                else ""
            )
            if overrides and "item_id_prefix" in overrides:
                item_id_prefix = overrides["item_id_prefix"]
            else:
                item_id_prefix = ""
            if hasattr(field_type, "__name__") and overrides and "item_id_mapping" in overrides:
                link_name = overrides["item_id_mapping"].get(values["name"]) or values["name"]
            else:
                link_name = values["name"]
            item_header = (
                f"`{values['name']}`"
                if not base_model
                else f"[`{values['name']}`](#{item_id_prefix}{link_name})"
            )
            item_required_marker = "(Required)" if values["required"] else "(Optional)"
            item_type_display = f"`{values['type']}`" if values.get("type") else ""
            item_description = (values["description"]).replace("\n", "<br>") + "."
            item_default = _defaults if not values["required"] else _must_be
            item_id = f"#{values['name']}" if not base_model else f"#_{values['name']}"
            item_toc_label = f"data-toc-label='{values['name']}'"
            item_css_cass = "class='reference-item'"
            parts = [
                f"###### {item_header}",
                "-",
                item_required_marker,
                item_type_display,
                item_description,
                item_default,
                "{",
                item_id,
                item_toc_label,
                item_css_cass,
                "}",
            ]
            rows.append(prefix + " ".join(p for p in parts if p))
    return "\n".join(rows)


def sub_schema_reference(match: re.Match) -> str:
    logger.debug("Generating schema reference for `%s`", match.group(2))
    options = yaml.safe_load("\n".join(row[4:] for row in match.group(3).split("\n")))
    logger.debug("Options: %s", options)
    return (
        generate_schema_reference(match.group(2), **(options or {}), prefix=match.group(1))
        + "\n\n"
    )


def expand_schema_references(text: str) -> str:
    """Expand #SCHEMA# placeholders in markdown text. Used by hooks when gen-files is not used."""
    return re.sub(
        r"( *)#SCHEMA#\s+(dstack\.[.a-z_0-9A-Z]+)\s*((?:\n {4}[^\n]+)*)\n",
        sub_schema_reference,
        text,
    )


def process_file(file: File):
    if not fnmatch(file.src_uri, FILE_PATTERN):
        return
    logger.debug("Looking for schema references in `%s`", file.src_uri)
    with mkdocs_gen_files.open(file.src_uri, "r") as f:
        text = f.read()
    # Pattern:
    # #SCHEMA# dstack.<module>.<model>
    #     overrides:
    #       name:
    #         required: true
    text = expand_schema_references(text)
    with mkdocs_gen_files.open(file.src_uri, "w") as f:
        f.write(text)


def main():
    # Processing sequentially since there is no speed up with concurrent processing
    for file in mkdocs_gen_files.files:
        process_file(file)


main()
