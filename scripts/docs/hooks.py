import json
import logging
import mimetypes
import os
import shutil

import yaml

mimetypes.add_type("text/plain", ".md")

log = logging.getLogger("mkdocs")

WELL_KNOWN_SKILLS_DIR = ".well-known/skills"
SKILL_SOURCE = "skill.md"
DISABLE_EXAMPLES_ENV = "DSTACK_DOCS_DISABLE_EXAMPLES"


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
    """Use README content for example stubs when rendering HTML."""
    return _get_materialized_content(page.file.src_uri, config)


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
                dest_path = os.path.join(site_dir, rel_path)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                shutil.copy2(src_path, dest_path)

    _write_well_known_skills(docs_dir, site_dir)


def _write_well_known_skills(docs_dir, site_dir):
    """Parse skill.md and write .well-known/skills/index.json. name and description come from frontmatter only."""
    skill_src = os.path.join(docs_dir, SKILL_SOURCE)
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
            "skill.md missing name or description in frontmatter; skipping .well-known/skills"
        )
        return

    out_dir = os.path.join(site_dir, WELL_KNOWN_SKILLS_DIR, name)
    os.makedirs(out_dir, exist_ok=True)
    shutil.copy2(skill_src, os.path.join(out_dir, "skill.md"))

    index_path = os.path.join(site_dir, WELL_KNOWN_SKILLS_DIR, "index.json")
    index = {"skills": [{"name": name, "description": description[:1024], "files": ["skill.md"]}]}
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)

    log.info(f"Published skill: {name}")
