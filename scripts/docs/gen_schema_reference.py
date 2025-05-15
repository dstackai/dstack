"""
Generates schema reference for dstack models.
"""

import importlib
import inspect
import logging
import re
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


def get_type(annotation: Type) -> str:
    if get_origin(annotation) is Annotated:
        return get_type(get_args(annotation)[0])
    if get_origin(annotation) is Union:
        # Optional is Union with None.
        # We don't want to show Optional[A, None] but just Optional[A]
        if annotation.__name__ == "Optional":
            args = ",".join(get_type(arg) for arg in get_args(annotation)[:-1])
        else:
            args = ",".join(get_type(arg) for arg in get_args(annotation))
        return f"{annotation.__name__}[{args}]"
    if get_origin(annotation) is Literal:
        return str(annotation).split(".", maxsplit=1)[-1]
    if get_origin(annotation) is list:
        return f"List[{get_type(get_args(annotation)[0])}]"
    if get_origin(annotation) is dict:
        return f"Dict[{get_type(get_args(annotation)[0])}, {get_type(get_args(annotation)[1])}]"
    return annotation.__name__


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
        values = dict(
            name=name,
            description=field.field_info.description,
            type=get_type(field.annotation),
            default=field.default,
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
                base_model = (
                    inspect.isclass(field_type)
                    and issubclass(field_type, BaseModel)
                    and not issubclass(field_type, Range)
                )
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
            item_optional_marker = "(Optional)" if not values["required"] else ""
            item_description = (values["description"]).replace("\n", "<br>") + "."
            item_default = _defaults if not values["required"] else _must_be
            item_id = f"#{values['name']}" if not base_model else f"#_{values['name']}"
            item_toc_label = f"data-toc-label='{values['name']}'"
            item_css_cass = "class='reference-item'"
            rows.append(
                prefix
                + " ".join(
                    [
                        f"###### {item_header}",
                        "-",
                        item_optional_marker,
                        item_description,
                        item_default,
                        "{",
                        item_id,
                        item_toc_label,
                        item_css_cass,
                        "}",
                    ]
                )
            )
    return "\n".join(rows)


def sub_schema_reference(match: re.Match) -> str:
    logger.debug("Generating schema reference for `%s`", match.group(2))
    options = yaml.safe_load("\n".join(row[4:] for row in match.group(3).split("\n")))
    logger.debug("Options: %s", options)
    return (
        generate_schema_reference(match.group(2), **(options or {}), prefix=match.group(1))
        + "\n\n"
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
    text = re.sub(
        r"( *)#SCHEMA#\s+(dstack\.[.a-z_0-9A-Z]+)\s*((?:\n {4}[^\n]+)*)\n",
        sub_schema_reference,
        text,
    )
    with mkdocs_gen_files.open(file.src_uri, "w") as f:
        f.write(text)


def main():
    # Processing sequentially since there is no speed up with concurrent processing
    for file in mkdocs_gen_files.files:
        process_file(file)


main()
