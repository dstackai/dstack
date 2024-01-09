"""
Generates schema reference for dstack models.
"""
import importlib
import logging
import re
from fnmatch import fnmatch
from typing import Annotated, Any, Dict, Literal, Type, Union, get_args, get_origin

import mkdocs_gen_files
import yaml
from mkdocs.structure.files import File

FILE_PATTERN = "docs/reference/*.md"
logger = logging.getLogger("mkdocs.plugins.dstack.schema")


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
    model_path: str, *, overrides: Dict[str, Dict[str, Any]] = None
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
                f"### {cls.__name__}",
                "",
            ]
        )
    rows.extend(
        [
            "| Property | Description | Type | Default value |",
            "| --- | --- | --- | --- |",
        ]
    )
    for name, field in cls.__fields__.items():
        values = dict(
            name=name,
            description=field.field_info.description,
            type=get_type(field.annotation),
            default=str(field.default),
            required=field.required,
        )
        if overrides and name in overrides:
            values.update(overrides[name])
        rows.append(
            "| %s | "
            % " | ".join(
                [
                    f"`{values['name']}`",
                    (values["description"] or "").replace("\n", "<br>"),
                    f"`{values['type']}`",
                    "*required*" if values["required"] else f"`{values['default']}`",
                ]
            )
        )
    return "\n".join(rows)


def sub_schema_reference(match: re.Match) -> str:
    logger.info("Generating schema reference for `%s`", match.group(1))
    try:
        options = yaml.safe_load("\n".join(row[4:] for row in match.group(2).split("\n")))
        logger.debug("Options: %s", options)
        return generate_schema_reference(match.group(1), **(options or {})) + "\n\n"
    except Exception as e:
        logger.error("Failed to generate schema reference for `%s`: %s", match.group(1), e)
        return match.group(0)


file: File
for file in mkdocs_gen_files.files:
    if not fnmatch(file.src_uri, FILE_PATTERN):
        continue
    logger.debug("Looking for schema references in `%s`", file.src_uri)
    with mkdocs_gen_files.open(file.src_uri, "r") as f:
        text = f.read()
    # Pattern:
    # #SCHEMA# dstack.<module>.<model>
    #     overrides:
    #       name:
    #         required: true
    text = re.sub(
        r"#SCHEMA#\s+(dstack\.[.a-z_0-9A-Z]+)\s*((?:\n {4}[^\n]+)*)\n", sub_schema_reference, text
    )
    with mkdocs_gen_files.open(file.src_uri, "w") as f:
        f.write(text)
