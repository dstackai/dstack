import importlib.util
import json
import logging
import mimetypes
import os
import posixpath
import re
import shutil
import sys
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

from mkdocs.structure.files import File

mimetypes.add_type("text/plain", ".md")

log = logging.getLogger("mkdocs")

WELL_KNOWN_SKILLS_DIR = ".well-known/skills"
SKILL_PATH = ("skills", "dstack", "SKILL.md")
DISABLE_LLM_TXT_ENV = "DSTACK_DOCS_DISABLE_LLM_TXT"
DISABLE_YAML_SCHEMAS_ENV = "DSTACK_DOCS_DISABLE_YAML_SCHEMAS"
SCHEMA_REFERENCE_PREFIX = "docs/reference/"
SWAGGER_TAG_ARG = r"(?:\s+tag=(?P<tag_quote>[\"'])(?P<tag>.*?)(?P=tag_quote))?"
SWAGGER_TOKEN = re.compile(rf"!!swagger(?:\s+(?P<path>[^\s<>&:!]+){SWAGGER_TAG_ARG})?!!")
SWAGGER_HTTP_TOKEN = re.compile(
    rf"!!swagger-http(?:\s+(?P<path>https?://[^\s!]+){SWAGGER_TAG_ARG})?!!"
)
SWAGGER_USAGE_MSG = (
    "Usage: '!!swagger <filename> [tag=\"tag name\"]!!' or "
    "'!!swagger-http <url> [tag=\"tag name\"]!!'. "
    "File must either exist locally and be placed next to the .md that contains "
    "the swagger statement, or be an http(s) URL."
)
HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
UNTAGGED_OPENAPI_TAG = "default"


def _expand_schema_references(text: str) -> str:
    """Lazy load gen_schema_reference by file path so it works regardless of sys.path."""
    hooks_dir = os.path.dirname(os.path.abspath(__file__))
    gen_path = os.path.join(hooks_dir, "gen_schema_reference.py")
    spec = importlib.util.spec_from_file_location("gen_schema_reference", gen_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {gen_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["gen_schema_reference"] = module
    spec.loader.exec_module(module)
    return module.expand_schema_references(text)


def _get_schema_expanded_content(rel_path, config, src_path=None):
    """Return expanded markdown for reference/**/*.md that contain #SCHEMA#, else None.
    If src_path is given (e.g. from on_post_build loop), read from it; else build path from config.
    """
    if os.environ.get(DISABLE_YAML_SCHEMAS_ENV):
        return None
    if not rel_path.startswith(SCHEMA_REFERENCE_PREFIX) or not rel_path.endswith(".md"):
        log.debug(f"Skipping {rel_path}: not in {SCHEMA_REFERENCE_PREFIX} or not .md")
        return None
    if src_path is None:
        repo_root = os.path.dirname(config["config_file_path"])
        docs_dir = config["docs_dir"]
        if not os.path.isabs(docs_dir):
            docs_dir = os.path.join(repo_root, docs_dir)
        src_path = os.path.join(docs_dir, rel_path.replace("/", os.sep))
    if not os.path.isfile(src_path):
        log.debug(f"Skipping {rel_path}: source file not found at {src_path}")
        return None
    try:
        with open(src_path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        log.debug(f"Skipping {rel_path}: error reading file: {e}")
        return None
    if "#SCHEMA#" not in text:
        log.debug(f"Skipping {rel_path}: no #SCHEMA# placeholders found")
        return None
    log.debug(f"Expanding schema references in {rel_path}")
    return _expand_schema_references(text)


def on_page_read_source(page, config):
    """Use expanded schema content for reference docs when rendering HTML."""
    rel_path = page.file.src_uri
    content = _get_schema_expanded_content(rel_path, config)
    if content is not None:
        return content
    return None


def on_page_markdown(markdown, page, config, files):
    """Render Swagger UI tokens with the project's preferred defaults."""
    while True:
        match = SWAGGER_TOKEN.search(markdown)
        is_http = False
        if match is None:
            match = SWAGGER_HTTP_TOKEN.search(markdown)
            is_http = True
        if match is None:
            return markdown
        markdown = _replace_swagger_token(markdown, match, is_http, page, files)


def _replace_swagger_token(markdown, match, is_http, page, files):
    pre_token = markdown[: match.start()]
    post_token = markdown[match.end() :]
    path = match.group("path")
    tag = match.groupdict().get("tag")
    operation_headings = ""
    if path is None:
        return _swagger_error(pre_token, post_token, SWAGGER_USAGE_MSG)
    if is_http:
        url = path
    else:
        try:
            api_file = Path(page.file.abs_src_path).parent / path
        except ValueError as exc:  # pragma: no cover
            return _swagger_error(pre_token, post_token, f"Invalid path. {exc.args[0]}")
        if not api_file.exists():
            return _swagger_error(pre_token, post_token, f"File {path} not found.")
        try:
            src_uri = api_file.relative_to(page.file.src_dir).as_posix()
        except ValueError as exc:
            return _swagger_error(
                pre_token,
                post_token,
                f"File {path} must be inside the docs directory. {exc.args[0]}",
            )
        new_file = File(src_uri, page.file.src_dir, page.file.dest_dir, False)
        url = _relative_url(page.file.dest_uri, new_file.dest_uri)
        for file in files:
            if file.dest_uri != new_file.dest_uri:
                continue
            if file.abs_src_path == new_file.abs_src_path:
                break
            return _swagger_error(
                pre_token,
                post_token,
                "Cannot use 2 different swagger files with same filename in same page.",
            )
        else:
            files.append(new_file)
        operation_headings = _openapi_operation_headings(api_file, tag)
    return pre_token + operation_headings + _swagger_html(url, tag) + post_token


def _relative_url(page_dest_uri: str, asset_dest_uri: str) -> str:
    page_dir = posixpath.dirname(page_dest_uri)
    return posixpath.relpath(asset_dest_uri, page_dir)


def _swagger_html(url: str, tag: str | None) -> str:
    tag_attr = ""
    if tag is not None:
        tag_attr = f' data-openapi-tag="{_escape_html_attr(tag)}"'
    return f"""

<div class="dstack-swagger-ui" data-openapi-url="{_escape_html_attr(url)}"{tag_attr}></div>

"""


def _openapi_operation_headings(api_file: Path, tag: str | None) -> str:
    try:
        schema = json.loads(api_file.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        log.warning(f"Cannot generate Swagger operation headings from {api_file}: {exc}")
        return ""

    operations = _get_openapi_operations(schema, tag)
    if not operations:
        return ""

    used_ids: set[str] = set()
    headings = [_openapi_operation_heading(operation, used_ids) for operation in operations]
    return "\n".join(headings) + "\n\n"


def _get_openapi_operations(
    schema: dict,
    tag: str | None,
) -> list[dict[str, str]]:
    operations = []
    for path, path_item in schema.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            method = method.lower()
            if method not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            operation_tags = operation.get("tags") or [UNTAGGED_OPENAPI_TAG]
            if tag is not None and tag not in operation_tags:
                continue
            operations.append(
                {
                    "method": method,
                    "path": path,
                    "summary": str(operation.get("summary") or ""),
                }
            )
    return operations


def _openapi_operation_heading(operation: dict[str, str], used_ids: set[str]) -> str:
    method = operation["method"]
    path = operation["path"]
    label = _openapi_operation_label(operation)
    anchor_id = _openapi_operation_anchor_id(method, path, used_ids)
    attrs = [
        f"#{anchor_id}",
        ".dstack-swagger-operation-anchor",
        f"data-toc-label={json.dumps(label)}",
        f"data-openapi-method={json.dumps(method)}",
        f"data-openapi-path={json.dumps(path)}",
    ]
    return f"## {label} {{ {' '.join(attrs)} }}"


def _openapi_operation_label(operation: dict[str, str]) -> str:
    summary = operation.get("summary", "").strip()
    if summary:
        return summary
    return operation["path"]


def _openapi_operation_anchor_id(method: str, path: str, used_ids: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", f"{method}-{path}".lower()).strip("-") or method
    anchor_id = base
    index = 2
    while anchor_id in used_ids:
        anchor_id = f"{base}-{index}"
        index += 1
    used_ids.add(anchor_id)
    return anchor_id


def _escape_html_attr(value: str) -> str:
    return escape(value, {'"': "&quot;"})


def _swagger_error(pre_token: str, post_token: str, message: str) -> str:
    return pre_token + escape(f"!! SWAGGER ERROR: {message} !!") + post_token


def on_config(config):
    if os.environ.get(DISABLE_YAML_SCHEMAS_ENV):
        log.warning("YAML schema reference generation is disabled")
    if os.environ.get(DISABLE_LLM_TXT_ENV):
        log.warning("llms.txt generation is disabled")
    return config


def on_post_build(config):
    """Copy .md files to site (raw) and write .well-known/skills index."""
    site_dir = config["site_dir"]
    docs_dir = config["docs_dir"]

    # Create .nojekyll to prevent GitHub Pages from ignoring .well-known directory
    nojekyll_path = os.path.join(site_dir, ".nojekyll")
    with open(nojekyll_path, "w") as f:
        f.write("")

    # Create _config.yml to explicitly include .well-known directory
    # This ensures Jekyll (if it runs) includes the .well-known directory
    config_yml_path = os.path.join(site_dir, "_config.yml")
    with open(config_yml_path, "w") as f:
        f.write('include: [".well-known"]\n')

    for root, _, files in os.walk(docs_dir):
        for file in files:
            if not file.endswith(".md"):
                continue

            src_path = os.path.join(root, file)
            rel_path = os.path.relpath(src_path, docs_dir).replace(os.sep, "/")
            content = _get_schema_expanded_content(rel_path, config, src_path=src_path)
            dest_path = os.path.join(site_dir, rel_path)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            if content is not None:
                # Write expanded schema content
                log.info(f"Expanding schema references in {rel_path}")
                with open(dest_path, "w", encoding="utf-8") as f:
                    f.write(content)
            else:
                # Just copy the file as-is
                shutil.copy2(src_path, dest_path)

    _write_well_known_skills(config, site_dir)
    _generate_llms_files(config, site_dir)


def _write_well_known_skills(config, site_dir):
    """Parse skills/dstack/SKILL.md and write .well-known/skills/index.json. name and description come from frontmatter only."""
    repo_root = os.path.dirname(config["config_file_path"])
    skill_src = os.path.join(repo_root, *SKILL_PATH)
    if not os.path.isfile(skill_src):
        return

    name = None
    description = None
    try:
        with open(skill_src, "r", encoding="utf-8") as f:
            text = f.read()
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    data = yaml.safe_load(parts[1])
                    if isinstance(data, dict):
                        name = data.get("name")
                        description = data.get("description")
    except Exception as e:
        log.error(f"Skill parsing error: {e}")

    if not name or not description:
        log.warning(
            "skills/dstack/SKILL.md missing name or description in frontmatter; skipping .well-known/skills"
        )
        return

    out_dir = os.path.join(site_dir, WELL_KNOWN_SKILLS_DIR, name)
    os.makedirs(out_dir, exist_ok=True)
    shutil.copy2(skill_src, os.path.join(out_dir, "SKILL.md"))
    # Serve skill at site root (both skill.md and SKILL.md) from skills/dstack/SKILL.md
    shutil.copy2(skill_src, os.path.join(site_dir, "skill.md"))
    shutil.copy2(skill_src, os.path.join(site_dir, "SKILL.md"))

    index_path = os.path.join(site_dir, WELL_KNOWN_SKILLS_DIR, "index.json")
    index = {
        "skills": [
            {"name": name, "description": description.strip()[:1024], "files": ["SKILL.md"]}
        ]
    }
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)

    log.info(f"Published skill: {name}")


def _generate_llms_files(config, site_dir):
    """Generate llms.txt and llms-full.txt using external script."""
    if os.environ.get(DISABLE_LLM_TXT_ENV):
        return

    repo_root = os.path.dirname(config["config_file_path"])

    # Import and run the generator
    hooks_dir = os.path.dirname(os.path.abspath(__file__))
    gen_path = os.path.join(hooks_dir, "gen_llms_files.py")
    spec = importlib.util.spec_from_file_location("gen_llms_files", gen_path)
    if spec is None or spec.loader is None:
        log.error(f"Cannot load {gen_path}")
        return
    module = importlib.util.module_from_spec(spec)
    sys.modules["gen_llms_files"] = module
    spec.loader.exec_module(module)

    try:
        # Pass mkdocs config to generator
        module.generate_llms_files(repo_root, site_dir, config)
        log.info("Generated llms.txt and llms-full.txt")
    except Exception as e:
        log.error(f"Failed to generate llms files: {e}")
