import importlib.util
import json
import logging
import mimetypes
import os
import shutil
import sys

import yaml

mimetypes.add_type("text/plain", ".md")

log = logging.getLogger("mkdocs")

WELL_KNOWN_SKILLS_DIR = ".well-known/skills"
SKILL_PATH = ("skills", "dstack", "SKILL.md")
DISABLE_EXAMPLES_ENV = "DSTACK_DOCS_DISABLE_EXAMPLES"
SCHEMA_REFERENCE_PREFIX = "docs/reference/"


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


def _get_materialized_content(rel_path, config):
    """Return README content for examples/**/index.md stubs, else None."""
    if os.environ.get(DISABLE_EXAMPLES_ENV):
        return None

    if rel_path.startswith("examples/") and rel_path.endswith("index.md"):
        repo_root = os.path.dirname(config["config_file_path"])
        example_dir = os.path.dirname(rel_path)
        readme_path = os.path.join(repo_root, example_dir, "README.md")

        if os.path.isfile(readme_path):
            with open(readme_path, "r", encoding="utf-8") as f:
                return f.read()
    return None


def on_page_read_source(page, config):
    """Use README content for example stubs and expanded schema for reference docs when rendering HTML."""
    rel_path = page.file.src_uri
    content = _get_materialized_content(rel_path, config)
    if content is not None:
        return content
    content = _get_schema_expanded_content(rel_path, config)
    if content is not None:
        return content
    return None


def on_page_context(context, page, config, nav):
    """Override edit_url only for example stubs so Edit points to the README; other pages use theme default from edit_uri."""
    repo_url = (config.get("repo_url") or "").rstrip("/")
    edit_uri = (config.get("edit_uri") or "edit/master/docs/").strip("/")
    if not repo_url:
        return context
    # edit_uri is e.g. "edit/master/docs" -> branch is second segment
    edit_parts = edit_uri.split("/")
    branch = edit_parts[1] if len(edit_parts) >= 2 else "master"

    rel_path = page.file.src_uri
    if rel_path.startswith("examples/") and rel_path.endswith("index.md"):
        example_dir = os.path.dirname(rel_path)
        page.edit_url = f"{repo_url}/edit/{branch}/{example_dir}/README.md"

    return context


def on_post_build(config):
    """Copy .md files to site (raw) and write .well-known/skills index."""
    site_dir = config["site_dir"]
    docs_dir = config["docs_dir"]

    for root, _, files in os.walk(docs_dir):
        for file in files:
            if not file.endswith(".md"):
                continue

            src_path = os.path.join(root, file)
            rel_path = os.path.relpath(src_path, docs_dir).replace(os.sep, "/")
            content = _get_materialized_content(rel_path, config)

            if content:
                clean_name = os.path.dirname(rel_path) + ".md"
                dest_path = os.path.join(site_dir, clean_name)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                with open(dest_path, "w", encoding="utf-8") as f:
                    f.write(content)
            else:
                # Check if this is a schema reference file that needs expansion
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
    shutil.copy2(skill_src, os.path.join(out_dir, "skill.md"))
    # Serve skill at site root (e.g. https://dstack.ai/skill.md) from skills/dstack/SKILL.md
    shutil.copy2(skill_src, os.path.join(site_dir, "skill.md"))

    index_path = os.path.join(site_dir, WELL_KNOWN_SKILLS_DIR, "index.json")
    index = {"skills": [{"name": name, "description": description[:1024], "files": ["skill.md"]}]}
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)

    log.info(f"Published skill: {name}")
