"""
Generates OpenAPI schema from dstack server app.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from dstack._internal.server.main import app
from dstack._internal.settings import DSTACK_VERSION

logger = logging.getLogger("mkdocs.plugins.dstack.openapi")
disable_env = "DSTACK_DOCS_DISABLE_OPENAPI_REFERENCE"
output_dir = Path("mkdocs/docs/reference/http")
openapi_path = output_dir / "openapi.json"

TAG_LIST_BEGIN = "<!-- BEGIN GENERATED HTTP API TAGS -->"
TAG_LIST_END = "<!-- END GENERATED HTTP API TAGS -->"
HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
UNTAGGED_TAG = "default"
OPENAPI_VERSION = "3.0.3"

if os.environ.get(disable_env):
    logger.warning("OpenAPI reference generation is disabled")
    exit(0)


def _write_tag_references(tags: list[str]) -> None:
    page_filenames = {_tag_page_filename(tag) for tag in tags}
    for tag in tags:
        page_filename = _tag_page_filename(tag)
        _write_text(output_dir / page_filename, _tag_page_content(tag))
    _remove_stale_tag_pages(page_filenames)
    _remove_stale_openapi_files()


def _update_index(tags: list[str]) -> None:
    index_path = output_dir / "index.md"
    if not index_path.exists():
        return
    text = index_path.read_text()
    tag_links = "\n".join(f"- [{_tag_title(tag)}]({_tag_page_filename(tag)})" for tag in tags)
    generated = f"{TAG_LIST_BEGIN}\n{tag_links}\n{TAG_LIST_END}"
    pattern = re.compile(f"{re.escape(TAG_LIST_BEGIN)}.*?{re.escape(TAG_LIST_END)}", re.S)
    new_text, count = pattern.subn(generated, text)
    if count == 0:
        logger.warning("HTTP API index is missing generated tag list markers")
        return
    _write_text(index_path, new_text)


def _remove_stale_openapi_files() -> None:
    for path in output_dir.glob("*.openapi.json"):
        path.unlink()


def _remove_stale_tag_pages(page_filenames: set[str]) -> None:
    for path in output_dir.glob("*.md"):
        if path.name != "index.md" and path.name not in page_filenames:
            path.unlink()


def _tag_page_content(tag: str) -> str:
    return f"""---
title: {_tag_title(tag)}
---

!!swagger {openapi_path.name} tag={json.dumps(tag)}!!
"""


def _tag_title(tag: str) -> str:
    return tag


def _tag_page_filename(tag: str) -> str:
    return f"{_tag_slug(tag)}.md"


def _tag_slug(tag: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", tag.lower()).strip("-") or UNTAGGED_TAG


def _write_json(path: Path, data: dict[str, Any]) -> None:
    _write_text(path, json.dumps(data) + "\n")


def _write_text(path: Path, content: str) -> None:
    if not path.exists() or path.read_text() != content:
        path.write_text(content)


def main() -> None:
    app.title = "OpenAPI Spec"
    app.servers = [
        {"url": "https://sky.dstack.ai", "description": "dstack Sky"},
        {"url": "http://localhost:3000", "description": "Local server"},
    ]
    app.version = DSTACK_VERSION or "0.0.0"
    app.openapi_version = OPENAPI_VERSION
    app.openapi_schema = None
    schema = app.openapi()
    tags = _get_tags(schema)

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(openapi_path, schema)
    _write_tag_references(tags)
    _update_index(tags)


def _get_tags(schema: dict[str, Any]) -> list[str]:
    tags = []
    for path, path_item in schema.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            for tag in operation.get("tags") or [UNTAGGED_TAG]:
                if tag not in tags:
                    tags.append(tag)
    return tags


main()
